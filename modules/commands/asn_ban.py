import asyncio
import datetime
import ipaddress
import logging
import re
from typing import List, Optional
import requests
import fido
from config import IRC
from models import asn_blacklist, session_scope
from modules.access import require_oper
from modules.networkprotection import asn_blacklist as asn_protection

# RIPEstat data API: the prefixes an AS announced in the last two weeks, and the AS holder's name.
ANNOUNCED_PREFIXES_URL = "https://stat.ripe.net/data/announced-prefixes/data.json"
AS_OVERVIEW_URL = "https://stat.ripe.net/data/as-overview/data.json"
SOURCE_APP = "fuelrats-fido"
HTTP_TIMEOUT = 10  # seconds
ASN_PATTERN = re.compile(r'AS(\d+)', re.IGNORECASE)

log = logging.getLogger(__name__)


class RIPEstatError(Exception):
    """A RIPEstat request that failed or did not answer with status 'ok'."""


def ripestat_get(url: str, params: dict) -> dict:
    """GET a RIPEstat data call and return its 'data' object. Blocking: run it in a worker thread."""
    try:
        response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as error:
        raise RIPEstatError(f"{type(error).__name__}") from error
    if body.get('status') != 'ok':
        raise RIPEstatError(f"status {body.get('status')!r}")
    return body.get('data') or {}


async def announced_prefixes(asn: str) -> List[str]:
    data = await asyncio.to_thread(ripestat_get, ANNOUNCED_PREFIXES_URL,
                                   {'resource': asn, 'sourceapp': SOURCE_APP})
    return [entry['prefix'] for entry in data.get('prefixes', []) if entry.get('prefix')]


async def holder_name(asn: str) -> Optional[str]:
    """The AS holder's name, or None if RIPEstat cannot tell."""
    try:
        data = await asyncio.to_thread(ripestat_get, AS_OVERVIEW_URL, {'resource': asn})
    except RIPEstatError as error:
        log.warning(f"No name for {asn}: {error}")
        return None
    return data.get('holder')


def split_arguments(args: List[str]):
    """Leading AS<n> arguments, then the rest of the line as the reason."""
    asns = []
    rest = list(args)
    while rest and ASN_PATTERN.fullmatch(rest[0]):
        asns.append(f"AS{ASN_PATTERN.fullmatch(rest[0]).group(1)}")
        rest.pop(0)
    return list(dict.fromkeys(asns)), ' '.join(rest).strip()


async def ban_one(asn: str, reason: str) -> str:
    """Fetch and store the prefixes of one AS; returns the reply line."""
    with session_scope() as session:
        banned = session.query(asn_blacklist.ASNBlacklist).filter(asn_blacklist.ASNBlacklist.asn == asn).first()
    if banned:
        return f"ASN Ban: {asn} is already banned."
    try:
        prefixes = await announced_prefixes(asn)
    except RIPEstatError as error:
        log.warning(f"Announced prefixes of {asn} not fetched: {error}")
        return f"ASN Ban: could not fetch the prefixes of {asn} from RIPEstat ({error}); nothing banned."
    if not prefixes:
        return f"ASN Ban: RIPEstat lists no announced prefixes for {asn}; nothing banned."
    networks = []
    for prefix in prefixes:
        try:
            networks.append(ipaddress.ip_network(prefix, strict=False))
        except ValueError:
            log.warning(f"Skipped a prefix of {asn} that is not a network")
    if not networks:
        return f"ASN Ban: RIPEstat lists no valid prefixes for {asn}; nothing banned."
    name = await holder_name(asn)
    timestamp = datetime.datetime.now()
    with session_scope() as session:
        for network in networks:
            session.add(asn_blacklist.ASNBlacklist(timestamp=timestamp, asn=asn, prefix=str(network.network_address),
                                                   cidr=str(network.prefixlen), reason=reason or None,
                                                   asn_name=name))
    count4 = sum(1 for network in networks if network.version == 4)
    count6 = len(networks) - count4
    return f"ASN Ban: Blocked {len(networks)} prefixes of {asn} ({name or 'unknown name'}): " \
           f"{count4} IPv4, {count6} IPv6."


@require_oper("ban networks")
async def ban_asn(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !asn_ban command: !asn_ban AS<n> [AS<n> ...] [reason]
    :param bot: bot instance
    :param args: ASNs (in the ASxxxx format) to ban, then the reason
    :return: The reply message
    """
    asns, reason = split_arguments(args)
    if not asns:
        return "Usage: " + IRC.commandPrefix + "asn_ban AS<number> [AS<number> ...] [reason]"
    replies = [await ban_one(asn, reason) for asn in asns]
    asn_protection.reload_prefixes()
    log.info(f"{sender} ran asn_ban for {', '.join(asns)}")
    for reply in replies:
        await bot.message(channel, reply)


@require_oper("test banned networks")
async def test_asn(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !asn_test command: report whether an address would be banned. Sends no G-line.
    """
    if not args:
        return "Usage: " + IRC.commandPrefix + "asn_test <ip address>"
    try:
        ip = str(ipaddress.ip_address(args[0]))
    except ValueError:
        return f"{args[0]} is not an IP address."
    item = asn_protection.check_ban(ip)
    if item is None:
        await bot.message(channel, f"ASN test: {ip} is not banned.")
    else:
        await bot.message(channel, f"ASN test: {ip} would be banned by {item.network} "
                                   f"({item.asn}: {item.asn_name}).")


@require_oper("unban networks")
async def unban_asn(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !unban_asn command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    for arg in args:
        if arg.startswith('AS'):
            with session_scope() as session:
                res = session.query(asn_blacklist.ASNBlacklist).\
                    filter(asn_blacklist.ASNBlacklist.asn == arg).first()
                if res:
                    log.info(f"Removing ban on {arg}.")
                    session.query(asn_blacklist.ASNBlacklist).\
                        filter(asn_blacklist.ASNBlacklist.asn == arg).delete()
            if res:
                asn_protection.reload_prefixes()
                await bot.message(channel, f"Unbanned ASN {arg}.")
            else:
                await bot.message(channel, f"{arg} is not a banned ASN.")
        else:
            await bot.message(channel, f"{arg} is not a valid argument, provide AS numbers prefixed with 'AS'")
    return

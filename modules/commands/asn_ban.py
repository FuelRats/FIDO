import asyncio
import logging
from typing import List
import requests
import fido
from models import asn_blacklist, session_scope
from modules.access import require_permission, Levels
from modules.networkprotection.asn_blacklist import protect_banned_asn
api_host = "https://api.bgpview.io/"
HTTP_TIMEOUT = 10  # seconds

log = logging.getLogger(__name__)


@require_permission(level=Levels.OP, message="'You are not allowed to ban networks.")
async def ban_asn(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !ban_asn command
    :param bot: bot instance
    :param args: A list of ASNs (in the ASxxxx format) to ban.
    :return: The reply message
    """

    pcount4 = 0
    pcount6 = 0
    notadded = 0
    for arg in args:
        if arg.startswith('AS'):
            with session_scope() as session:
                res = session.query(asn_blacklist.ASNBlacklist).\
                    filter(asn_blacklist.ASNBlacklist.asn == arg).first()
            if res:
                log.info(f"{arg} is already blacklisted!")
                notadded += 1
                continue
            response = (await asyncio.to_thread(requests.get, f"{api_host}asn/{arg}/prefixes",
                                                timeout=HTTP_TIMEOUT)).json()
            if response['status'] == 'ok':
                with session_scope() as session:
                    for prefix in response['data']['ipv4_prefixes']:
                        new = asn_blacklist.ASNBlacklist(asn=arg, prefix=prefix['ip'],
                                                         cidr=prefix['cidr'], asn_name=prefix['name'])
                        session.add(new)
                        pcount4 += 1
                    for prefix in response['data']['ipv6_prefixes']:
                        new = asn_blacklist.ASNBlacklist(asn=arg, prefix=prefix['ip'],
                                                         cidr=prefix['cidr'], asn_name=prefix['name'])
                        session.add(new)
                        pcount6 += 1
    await bot.message(channel, f"ASN Ban: Blocked {pcount4} IPv4 prefixes, {pcount6} IPv6 prefixes.")


@require_permission(level=Levels.OP, message="'You are not allowed to test banned networks.")
async def test_asn(bot: fido, channel: str, sender: str, args: List[str]):
    res = await protect_banned_asn(bot, sender, args[0])
    if res:
        await bot.message(channel, f"ASN ban check returns true.")
    else:
        await bot.message(channel, f"ASN ban check returns false.")


@require_permission(level=Levels.OP, message="'You are not allowed to list banned networks.")
async def list_banned(bot: fido, channel: str, sender: str, args: List[str]):
    return


@require_permission(level=Levels.OP, message="'You are not allowed to unban networks.")
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
                await bot.message(channel, f"Unbanned ASN {arg}.")
            else:
                await bot.message(channel, f"{arg} is not a banned ASN.")
        else:
            await bot.message(channel, f"{arg} is not a valid argument, provide AS numbers prefixed with 'AS'")
    return

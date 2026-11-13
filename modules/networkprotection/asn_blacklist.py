import ipaddress
import logging
from typing import NamedTuple, Optional

import fido
from models import session_scope
from models.asn_blacklist import ASNBlacklist

log = logging.getLogger(__name__)

# A connecting address is widened to this network before the overlap test with the banned prefixes.
CLIENT_PREFIXLEN = {4: 24, 6: 56}


class BannedPrefix(NamedTuple):
    network: ipaddress.IPv4Network | ipaddress.IPv6Network
    asn: str
    asn_name: str


_prefixes: Optional[list] = None  # BannedPrefix list, loaded on first use


def load_prefixes() -> list:
    """Read every banned prefix from the DB into memory. Rows that do not parse are skipped and counted."""
    with session_scope() as session:
        rows = [(row.prefix, row.cidr, row.asn, row.asn_name) for row in session.query(ASNBlacklist)]
    prefixes = []
    skipped = 0
    for prefix, cidr, asn, asn_name in rows:
        try:
            network = ipaddress.ip_network(f"{prefix}/{cidr}", strict=False)
        except ValueError:
            skipped += 1
            continue
        prefixes.append(BannedPrefix(network, asn, asn_name))
    if skipped:
        log.warning(f"Skipped {skipped} banned prefixes that are not valid networks")
    log.info(f"Loaded {len(prefixes)} banned prefixes")
    return prefixes


def reload_prefixes():
    """Re-read the banned prefixes; call after the asn_blacklist table changed."""
    global _prefixes
    _prefixes = load_prefixes()


def forget_prefixes():
    """Drop the loaded prefixes, so the next check reads the DB again."""
    global _prefixes
    _prefixes = None


def check_ban(hostmask: str) -> Optional[BannedPrefix]:
    """
    The banned prefix that overlaps the /24 (IPv4) or /56 (IPv6) around hostmask, or None.
    :param hostmask: Hostmask (Or rather just IP) of user
    """
    global _prefixes
    try:
        ip = ipaddress.ip_address(hostmask)
    except ValueError:
        log.warning("Client connected without an IP address, ASN check skipped")
        return None
    network = ipaddress.ip_network(f"{ip}/{CLIENT_PREFIXLEN[ip.version]}", strict=False)
    if _prefixes is None:
        _prefixes = load_prefixes()
    for item in _prefixes:
        if item.network.version == network.version and network.overlaps(item.network):
            return item
    return None


async def protect_banned_asn(bot: fido, nickname, hostmask):
    item = check_ban(hostmask)
    if item is None:
        return False
    await bot.message("#opers", f"ASN BAN: User {nickname} connecting from "
                                f"banned network {item.asn}: {item.asn_name} "
                                f"({item.network})")
    await bot.raw(f"GLINE *@{hostmask} 7d You are connecting from a banned VPN network, which is not "
                  f"currently allowed. If you believe this is in error, please contact ops@fuelrats.com\n")
    return True

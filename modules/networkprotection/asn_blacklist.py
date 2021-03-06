import socket
import fido
import ipaddress
from models import SessionManager
from models.asn_blacklist import ASNBlacklist


async def protect_banned_asn(bot: fido, nickname, hostmask):
    res, network = await check_ban(bot, nickname, hostmask)
    if res:
        await bot.message("#opers", f"ASN BAN: User {nickname} connecting from "
                                    f"banned network {network.asn}: {network.asn_name} "
                                    f"({network.prefix}/{network.cidr})")
        await bot.raw(f"GLINE *@{hostmask} 7d You are connecting from a banned VPN network, which is not "
                      f"currently allowed. If you believe this is in error, please contact ops@fuelrats.com\n")
        return True
    return False


async def check_ban(bot: fido, nickname, hostmask):
    """
    Check IPs against ASN blacklists.
    :param bot: bot instance
    :param nickname: Nickname of user
    :param hostmask: Hostmask (Or rather just IP) of user
    :return: Nothing.
    """
    sessionmanager = SessionManager()
    session = sessionmanager.session
    try:
        ip = ipaddress.ip_address(hostmask)
    except ValueError:
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(hostmask))
        except socket.gaierror:
            print(f"Unable to make sense of hostmask: {hostmask}")
    if ip.version == 6:
        network = ipaddress.ip_network(f"{hostmask}/56", False)
    else:
        network = ipaddress.ip_network(f"{hostmask}/24", False)
    prefixes = session.query(ASNBlacklist).all()

    for item in prefixes:
        n2 = ipaddress.ip_network(f"{item.prefix}/{item.cidr}")
        if network.overlaps(n2):
            return True, item
    return False, None

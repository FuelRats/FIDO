import fido
from modules import configmanager, sessiontracker
from modules.networkprotection import asn_blacklist


async def on_connect(bot: fido, message: str, match):
    """
    Handler for connect.LOCAL_CLIENT_CONNECT and connect.REMOTE_CLIENT_CONNECT: record the session,
    report clones and G-Line clients from banned ASNs. Both use the client's IP, never its hostname.
    :param bot: bot instance
    :param message: notice text after the frame
    :param match: match of the connect pattern
    """
    nick = match.group('nick')
    ip = match.group('ip')
    await sessiontracker.check_clone(bot, nick, ip)
    await asn_blacklist.protect_banned_asn(bot, nick, ip)


def _client_host(client: str) -> str:
    """The host of nick!user@host, or the address of an unregistered client shown as [address]."""
    host = client.rpartition('@')[2]
    if host.startswith('[') and host.endswith(']'):
        return host[1:-1]
    return host


async def on_qline(bot: fido, message: str, match):
    """
    Handler for nick.QLINE_NICK_LOCAL_ATTEMPT: report the refused nick to the oper channel.
    :param bot: bot instance
    :param message: notice text after the frame
    :param match: match of patterns.PATTERNS['nick.QLINE_NICK_LOCAL_ATTEMPT']
    """
    if not configmanager.gate_open(configmanager.GATE_OPERS_REPORTS):
        return
    nick = match.group('nick')
    host = match.group('ip') or _client_host(match.group('client'))
    reason = match.group('reason')
    await bot.message(bot.get_oper_channel(),
                      f"{bot.colour_red('QLINE')} {nick}@{host} refused nick: {reason}")

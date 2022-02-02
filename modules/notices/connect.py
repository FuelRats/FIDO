import re
import fido
from modules import sessiontracker
from modules.networkprotection import asn_blacklist

regex = re.compile(
    '.* (Client connecting: (?P<nick>[A-Za-z0-9_´|\[\]]*) '
    '\((?P<user>[A-Za-z0-9_´|\[\]]*)@(?P<host>[A-Za-z0-9.:_\-]*)\) \[(?P<filter>[0-9.:A-F-a-f]*)\])',
    re.I)

qline = re.compile(
    '.* Forbidding Q-lined nick (?P<nick>[A-Za-z0-9_´|\[\]]*) from \[(?P<host>[0-9.:A-F-a-f]*)\] '
    '\((?P<reason>.*)\)', re.I)


async def on_connect(bot: fido, message: str, match):
    """
    Handler for connection notification to the server,
    saving sessions.
    :param bot: bot instance
    :param message: message
    :param match: regex match
    :return: Optional, returns if a clone is detected
    """

    nick = match.group('nick')
    hostmask = match.group('host')
    await sessiontracker.check_clone(bot, nick, hostmask)
    await asn_blacklist.protect_banned_asn(bot, nick, hostmask)


async def on_qline(bot: fido, message: str, match):
    """
    Handler for qlined connections
    :param bot: bot instance
    :param message: message
    :param match: regex match
    :return: The reply message
    """
    operchannel = bot.get_oper_channel()
    nick = match.group('nick')
    host = match.group('host')
    reason = match.group('reason')
    await bot.message(operchannel,
                      f"{bot.colour_red('QLINE')} {nick}@{host} refused connection: {reason}")


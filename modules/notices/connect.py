import re
import fido
from modules import sessiontracker

regex = re.compile(
    '.* (Client connecting: (?P<nick>[A-Za-z0-9_´|\[\]]*) '
    '\((?P<user>[A-Za-z0-9_´|\[\]]*)@(?P<host>[A-Za-z0-9.:_\-]*)\)'
    ' \[(?P<filter>[0-9.:A-F-a-f]*)\])',
    re.I)


async def on_connect(bot: fido, message: str, match):
    """
    Handler for connection notification to the server,
    saving sessions.
    :param bot: bot instance
    :param message: message
    :param match: regex match
    :return: Optional, returns if a clone is detected
    """
    print("Matched a connect regexp")
    nick = match.group('nick')
    hostmask = match.group('host')
    print("Calling sessiontracker.")
    await sessiontracker.check_clone(bot, nick, hostmask)

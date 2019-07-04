from typing import List

import re
import fido

regex = re.compile(
    '.*Received KILL message for (?P<nick>[A-Za-z0-9_´|\[\]]*)!(?P<user>[A-Za-z0-9_´|\[\]]*)@(?P<host>[A-Za-z0-9.:_\-]*) from (?P<sender>[A-Za-z0-9_´|\[\]]*) Path: [A-Za-z0-9._\-]*![A-Za-z0-9_´|\[\]]* \((?P<reason>.*)\)$',
    re.I)


async def on_kill(bot: fido, message: str, match):
    """
    Handler for the !join command
    :param bot: bot instance
    :param message: message
    :param match: regex match
    :return: The reply message
    """
    nick = match.group('nick')
    host = match.group('host')
    sender = match.group('sender')
    reason = match.group('reason')
    await bot.message("#opers",
                      f"{bot.colour_red('KILL')} {nick} ({host}) was killed by {sender} with message: {reason}")

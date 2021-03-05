import re
import fido
from models import SessionManager, config

regex = re.compile('.* G-Line added for (?P<user>[A-Za-z0-9_´|\*\[\]].*)@(?P<host>[A-Za-z0-9.:_\-].*) on '
                   '(?P<timestamp>.*) \(from (?P<sender>[A-Za-z0-9_´|\[\]].*) to expire at (?P<expiration>.*): '
                   '(?P<reason>.*)\)', re.I)

perma = re.compile('.* G-Line added for (?P<user>[A-Za-z0-9_´|\*\[\]].*)@(?P<host>[A-Za-z0-9.:_\-].*) on '
                   '(?P<timestamp>.*) \(from (?P<sender>[A-Za-z0-9_´|\[\]].*): '
                   '(?P<reason>.*)\)', re.I)


async def on_gline(bot: fido, message: str, match):
    """
    Handler for the gline notice
    :param bot: bot instance
    :param message: message
    :param match: regex match
    :return: The reply message
    """
    operchannel = bot.get_oper_channel()
    user = match.group('user')
    host = match.group('host')
    sender = match.group('sender')
    reason = match.group('reason')
    expiration = match.group('expiration')
    await bot.message(operchannel,
                      f"{bot.colour_red('GLINE')} {user}@{host} was G-LINED by {sender} until {expiration} "
                      f"with message: {reason}")


async def on_perma(bot: fido, message: str, match):
    """
    Handler for the permanent gline notice
    :param bot: bot instance
    :param message: message
    :param match: regex match
    :return: The reply message
    """
    operchannel = bot.get_oper_channel()
    user = match.group('user')
    host = match.group('host')
    sender = match.group('sender')
    reason = match.group('reason')
    if 'to expire at' in sender:
        return  # Don't trigger if the regmatch is a false positive from a timed gline.
    await bot.message(operchannel,
                      f"{bot.colour_red('GLINE')} {user}@{host} was PERMANENTLY G-LINED by {sender} "
                      f"with message: {reason}")


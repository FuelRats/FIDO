import re
import fido

regex = re.compile('.* Failed OPER attempt by (?P<nick>[A-Za-z0-9_´|\[\]]*) \((?P<user>[A-Za-z0-9_´|\[\]]*)@(?P<host>[A-Za-z0-9.:_\-]*)\) \[(?P<reason>[0-9.:A-F-a-f]*)\]')


async def on_oper_fail(bot: fido, match):
    """
    Handler for failed oper notices
    :param bot: bot instance
    :param message: message
    :param match: regex match
    :return: Nothing
    """
    operchannel = bot.get_oper_channel()
    nick = match.group('nick')
    host = match.group('host')
    sender = match.group('user')
    reason = match.group('reason')
    await bot.message(operchannel,
                      f"Failed {bot.colour_red('OPER')} by {nick} ({host}): {reason}")
    return

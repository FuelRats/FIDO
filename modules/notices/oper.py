import fido
from modules import configmanager


async def on_oper_fail(bot: fido, message: str, match):
    """
    Handler for oper.OPER_FAILED: report the failed attempt to the oper channel.
    :param bot: bot instance
    :param message: notice text after the frame
    :param match: match of patterns.PATTERNS['oper.OPER_FAILED']
    """
    if not configmanager.gate_open(configmanager.GATE_OPERS_REPORTS):
        return
    nick, _, userhost = match.group('client').partition('!')
    host = userhost.rpartition('@')[2]
    reason = match.group('reason')
    await bot.message(bot.get_oper_channel(),
                      f"Failed {bot.colour_red('OPER')} by {nick} ({host}): {reason}")

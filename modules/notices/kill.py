import fido
from modules import configmanager


async def on_kill(bot: fido, message: str, match):
    """
    Handler for kill.KILL_COMMAND: report the kill to the oper channel.
    :param bot: bot instance
    :param message: notice text after the frame
    :param match: match of patterns.PATTERNS['kill.KILL_COMMAND']
    """
    if not configmanager.gate_open(configmanager.GATE_OPERS_REPORTS):
        return
    nick, _, userhost = match.group('target').partition('!')
    host = userhost.rpartition('@')[2]
    sender = match.group('by')
    reason = match.group('reason')
    await bot.message(bot.get_oper_channel(),
                      f"{bot.colour_red('KILL')} {nick} ({host}) was killed by {sender} with message: {reason}")

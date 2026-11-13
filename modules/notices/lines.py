import fido
from modules import configmanager

GLINE_TYPE = 'G-Line'
PERMANENT = 'permanent'


async def on_tkl_add(bot: fido, message: str, match):
    """
    Handler for tkl.TKL_ADD: report G-Lines (and Soft G-Lines) to the oper channel. G-Lines FIDO set
    itself are skipped; protect_banned_asn already reported them as ASN BAN.
    :param bot: bot instance
    :param message: notice text after the frame
    :param match: match of patterns.PATTERNS['tkl.TKL_ADD']
    """
    if GLINE_TYPE not in (match.group('type') or ''):
        return
    by = match.group('by')
    if bot.is_same_nick(by.partition('!')[0], bot.nickname):
        return
    if not configmanager.gate_open(configmanager.GATE_OPERS_REPORTS):
        return
    mask = match.group('mask')
    reason = match.group('reason')
    duration = match.group('duration')
    if duration == PERMANENT:
        text = f"{bot.colour_red('GLINE')} {mask} was PERMANENTLY G-LINED by {by} with message: {reason}"
    else:
        text = f"{bot.colour_red('GLINE')} {mask} was G-LINED by {by} for {duration} with message: {reason}"
    await bot.message(bot.get_oper_channel(), text)

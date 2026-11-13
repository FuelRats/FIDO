import fido
from modules import configmanager, sms

# Filters whose name holds one of these words are the ops alert filters (any case).
OPS_SIGNAL_WORDS = ('opsignal', 'opssignal')
OPS_GROUP = 'ops'
NO_ACTION = 'action not shown'


def is_ops_signal(filter_text: str) -> bool:
    lowered = filter_text.lower()
    return any(word in lowered for word in OPS_SIGNAL_WORDS)


async def on_spamfilter_trigger(bot: fido, message: str, match):
    """
    Handler for tkl.SPAMFILTER_MATCH. An ops alert filter posts OPS1GNAL to the oper channel and
    texts the ops group; any other filter posts a SPAMFILTER line. Nick, filter and target come from
    the server-written head. A hit cut off by the line limit matches only the head pattern, which
    has no reason or action; a client can shape the end of a cut hit, so the SMS never holds the
    reason.
    :param bot: bot instance
    :param message: notice text after the frame
    :param match: match of the spamfilter pattern or of its head-only fallback
    """
    groups = match.groupdict()
    nick = groups['nick']
    filter_text = groups['filter']
    target = groups['target'] or groups['cmd'] or '-'
    reason = groups.get('reason')
    reports_on = configmanager.gate_open(configmanager.GATE_OPERS_REPORTS)

    if not is_ops_signal(filter_text):
        if reports_on:
            action = groups.get('action') or NO_ACTION
            await bot.message(bot.get_oper_channel(),
                              f"SPAMFILTER {nick} -> {target} matched '{filter_text}' ({action})")
        return

    origin = f"by {nick} in {target}"
    if reports_on:
        report = f"{origin}: {reason}" if reason else origin
        await bot.message(bot.get_oper_channel(), f"OPS1GNAL {report}")
    if configmanager.gate_open(configmanager.GATE_SMS):
        await sms.send_to_group(OPS_GROUP, f"OPSIGNAL {origin}")

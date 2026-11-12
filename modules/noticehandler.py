"""
Server notice dispatch: strip the formatting, split the frame, look up the event ID, match the
event's pattern and call its handler. fido.FIDO.on_notice passes only server notices addressed to
FIDO.
"""
import collections
import logging
import time

import fido
from modules.notices import connect, frame, kill, lines, link, oper, patterns, spamfilter

log = logging.getLogger(__name__)

HANDLERS = {
    'tkl.TKL_ADD': lines.on_tkl_add,
    'kill.KILL_COMMAND': kill.on_kill,
    'nick.QLINE_NICK_LOCAL_ATTEMPT': connect.on_qline,
    'oper.OPER_FAILED': oper.on_oper_fail,
    'tkl.SPAMFILTER_MATCH': spamfilter.on_spamfilter_trigger,
    'connect.LOCAL_CLIENT_CONNECT': connect.on_connect,
    'connect.REMOTE_CLIENT_CONNECT': connect.on_connect,
    'link.LINK_UNRELIABLE': link.on_unreliable,
    'link.LINK_DISCONNECTED': link.on_disconnected,
    'link.SERVER_LINKED': link.on_linked,
}

UNPARSED_REPORT_INTERVAL = 3600  # seconds between two summaries of unparsed notices

unparsed = collections.Counter()  # unparsed notices per event since the last summary
_last_report = time.monotonic()


def report_unparsed(now=None):
    """Log the unparsed counts once UNPARSED_REPORT_INTERVAL has passed, if any, and reset them."""
    global _last_report
    now = time.monotonic() if now is None else now
    if now - _last_report < UNPARSED_REPORT_INTERVAL:
        return
    _last_report = now
    if not unparsed:
        return
    counts = ', '.join(f"{event} {count}" for event, count in sorted(unparsed.items()))
    log.warning(f"unparsed notices in the last {UNPARSED_REPORT_INTERVAL // 60} minutes: {counts}")
    unparsed.clear()


async def handle_notice(bot: fido, message: str):
    """
    Dispatch one server notice. Events without a handler are ignored. A dispatched event whose
    pattern does not match is logged as unparsed, without its text.
    :param bot: bot instance
    :param message: the notice text as received
    """
    report_unparsed()
    framed = frame.split_frame(frame.strip_formatting(message))
    if framed is None:
        return
    event = framed.group('event')
    handler = HANDLERS.get(event)
    if handler is None:
        return
    if framed.group('cont') == frame.CONTINUATION:
        log.debug(f"Skipped a continuation line of {event}")
        return
    text = framed.group('msg')
    match = patterns.match_notice(event, text)
    if match is None:
        unparsed[event] += 1
        log.warning(f"unparsed {event}")
        return
    await handler(bot, text, match)

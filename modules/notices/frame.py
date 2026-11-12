"""
The frame of an UnrealIRCd 6 server notice: `subsystem.EVENT[+] [level] text`, with IRC colour
codes around the event ID and the level.

Standard library only and no FIDO imports: tools/replay_notices.py is shipped as
`cat modules/notices/frame.py modules/notices/patterns.py tools/replay_notices.py`.
"""
import re

FORMATTING = re.compile(r"[\x02\x0f\x16\x1d\x1f]|\x03(?:\d{1,2}(?:,\d{1,2})?)?")
FRAME = re.compile(r"^(?P<event>[a-z0-9_-]+\.[A-Z0-9_]+)(?P<cont>\+?) \[(?P<level>[a-z]+)\] (?P<msg>.*)$")
CONTINUATION = '+'


def strip_formatting(s):
    """s without IRC bold, colour, reverse, italic, underline and reset codes."""
    return FORMATTING.sub('', s)


def split_frame(s):
    """
    The frame of a notice with its formatting stripped, as a match with the groups event, cont,
    level and msg; None if s is not framed. cont is CONTINUATION on every line of a multi-line
    message except the last.
    """
    return FRAME.match(s)

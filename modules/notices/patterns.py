"""
Regexes for the text of the UnrealIRCd 6 server notices FIDO acts on, keyed by event ID. Each one
matches the msg part of a frame (modules/notices/frame.py) after formatting is stripped. The
templates are the same in UnrealIRCd 6.2.6 and 6.2.7.1.

Standard library only and no FIDO imports: tools/replay_notices.py is shipped as
`cat modules/notices/frame.py modules/notices/patterns.py tools/replay_notices.py`.
"""
import re

# A spamfilter hit is server-written except for the client's text, which it quotes raw after
# `[cmd: <command>[ <target>]: '`, and the server cuts every line it sends at the line limit. So the
# filter name ends at the first `': [cmd: ` or `': [reason: ` after `matches filter '` (the head),
# and the reason and action are read only where they end the line (the tail).
SPAMFILTER_HEAD = (r"^\[Spamfilter\] (?P<nick>[^!\s]+)!(?P<user>[^@\s]+)@(?P<host>\S+) matches filter "
                   r"'(?P<filter>(?:(?!': \[(?:cmd|reason): ).)*)': ")
SPAMFILTER_CMD = r"\[cmd: (?P<cmd>[A-Z]+)(?: (?P<target>[^:\]\s]+))?"
SPAMFILTER_TAIL = (r"\[reason: (?P<reason>.*)\] \[action: (?P<action>[^\]]+)\]"
                   r"(?: \[spamfilter-id: [A-Z0-9]+\])?$")

PATTERN_SOURCES = {
    "tkl.TKL_ADD": r"^(?P<type>.+?) added: '(?P<mask>[^']*)' \[(?:reason: (?P<reason>.*)|types: (?P<types>[^\]]*))\] \[by: (?P<by>.*?)\] \[duration: (?P<duration>[^\]]+)\](?: \[id: (?P<id>[A-Z0-9]+)\])?(?: \[spamfilter-id: (?P<sfid>[A-Z0-9]+)\])?$|^Spamfilter added: '(?P<sf>.*)' \[type: ",
    "kill.KILL_COMMAND": r"^Client killed: (?P<target>\S+) \[by: (?P<by>.*?)\] \((?P<reason>.*)\)$",
    "nick.QLINE_NICK_LOCAL_ATTEMPT": r"^Attempt to use banned nick (?P<nick>\S+) (?:by (?P<client>\S+)|\[(?P<ip>[^\]]+)\]) blocked \((?P<reason>.*)\)$",
    "oper.OPER_FAILED": r"^Failed OPER attempt by (?P<client>\S+) \[reason: (?P<reason>[^\]]*)\] \[oper-block: (?P<block>[^\]]*)\]",
    "tkl.SPAMFILTER_MATCH": SPAMFILTER_HEAD + r"(?:" + SPAMFILTER_CMD + r"(?:: '(?P<text>.*)')?\] )?" + SPAMFILTER_TAIL,
    "connect.LOCAL_CLIENT_CONNECT": r"^Client connecting: (?P<nick>\S+) \((?P<user>[^@\s]+)@(?P<host>[^)\s]+)\) \[(?P<ip>[^\]\s]+)\]",
    "connect.REMOTE_CLIENT_CONNECT": r"^Client connecting: (?P<nick>\S+) \((?P<user>[^@\s]+)@(?P<host>[^)\s]+)\) \[(?P<ip>[^\]\s]+)\]",
    "link.LINK_UNRELIABLE": r"^Warning, no response from (?P<server>\S+) for (?P<seconds>\d+) seconds$",
    "link.LINK_DISCONNECTED": r"^Lost server link to (?P<server>\S+) \[(?P<ip>[^\]]*)\]: (?P<reason>.*)$",
    "link.SERVER_LINKED": r"^Server linked: (?P<src>\S+) -> (?P<dst>\S+)(?: \[secure: (?P<tls>[^\]]+)\])?$",
}

# A spamfilter hit longer than the line limit loses its tail, [reason:] and [action:] included.
# The head still names the client, the filter and the target.
FALLBACK_SOURCES = {
    "tkl.SPAMFILTER_MATCH": SPAMFILTER_HEAD + r"(?:" + SPAMFILTER_CMD + r")?",
}

PATTERNS = {event: re.compile(source) for event, source in PATTERN_SOURCES.items()}
FALLBACKS = {event: re.compile(source) for event, source in FALLBACK_SOURCES.items()}


def match_notice(event, msg):
    """
    The match of msg against the pattern for event, else against its fallback; None if neither
    matches or event has no pattern.
    """
    pattern = PATTERNS.get(event)
    if pattern is None:
        return None
    found = pattern.match(msg)
    if found is None and event in FALLBACKS:
        found = FALLBACKS[event].match(msg)
    return found

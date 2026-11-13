"""
Replay logged server notices through FIDO's notice patterns and print counts only, never line
content. It imports nothing from FIDO and runs as one script made by concatenation:

    cat modules/notices/frame.py modules/notices/patterns.py tools/replay_notices.py \
        | python3 -I - <log> [<log> ...]

Each log may be plain or gzip. Two line shapes are read:
- FIDO DEBUG lines holding a received notice: `<< [@tags ]:<source> NOTICE <target> :<text>`, from
  a server source only (a dot in the source nick, as in fido.FIDO.on_notice);
- UnrealIRCd text log lines (ircd.log): `[<time>] <server> <subsystem.EVENT> <level>: <text>`.

Per dispatched event and per shape it prints matched/total, or "no data" when no line arrived.
SPAMFILTER_MATCH has two rows: the full pattern, and full or head-only (what FIDO dispatches).
Exit status: 0 when every event with data matched in full or head-only, 1 when one did not,
2 when the script was not concatenated as above or no path was given.

strip_formatting, split_frame and CONTINUATION come from frame.py, PATTERNS and FALLBACKS from
patterns.py, which precede this file in the concatenation.
"""
import collections
import gzip
import re
import sys
import zlib

REPLAY_NOTICE_LINE = re.compile(r":<< (@\S+ )?:(\S+) NOTICE (\S+) :(.*)$")
REPLAY_IRCD_LINE = re.compile(r"^\[[^\]]+\] \S+ (?P<event>[a-z0-9_-]+\.[A-Z0-9_]+) (?P<level>[a-z]+): (?P<msg>.*)$")
REPLAY_GZIP_MAGIC = b'\x1f\x8b'
REPLAY_SHAPES = ('fido.log', 'ircd.log')
REPLAY_HEAD_SUFFIX = ' head'
REPLAY_USAGE = ("usage: cat modules/notices/frame.py modules/notices/patterns.py tools/replay_notices.py"
                " | python3 -I - <log> [<log> ...]\n")
REPLAY_EXIT_OK = 0
REPLAY_EXIT_BELOW = 1
REPLAY_EXIT_USAGE = 2
REPLAY_CELL_WIDTH = 24  # a cell with 7-digit counts, "1234567/1234567 100.0%", and a gap


def replay_open(path):
    """A text reader for path, gunzipping it when it starts with the gzip magic bytes."""
    with open(path, 'rb') as probe:
        compressed = probe.read(len(REPLAY_GZIP_MAGIC)) == REPLAY_GZIP_MAGIC
    if compressed:
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace')
    return open(path, 'r', encoding='utf-8', errors='replace')


def replay_extract(line):
    """(shape, event, msg, continuation) for a notice or ircd.log line, else None."""
    if ' NOTICE ' in line:
        found = REPLAY_NOTICE_LINE.search(line)
        if found is None:
            return None
        source_nick = found.group(2).split('!')[0].split('@')[0]
        if '.' not in source_nick:
            return None
        framed = split_frame(strip_formatting(found.group(4)))
        if framed is None:
            return None
        return (REPLAY_SHAPES[0], framed.group('event'), framed.group('msg'),
                framed.group('cont') == CONTINUATION)
    if line.startswith('['):
        found = REPLAY_IRCD_LINE.match(line)
        if found is None:
            return None
        return REPLAY_SHAPES[1], found.group('event'), found.group('msg'), False
    return None


class ReplayCounts:
    def __init__(self):
        self.total = collections.Counter()  # (event, shape)
        self.full = collections.Counter()
        self.dispatched = collections.Counter()  # full or head-only
        self.continuations = 0
        self.files = 0
        self.lines = 0
        self.skipped = []  # (path, error class name)

    def add(self, shape, event, msg):
        pattern = PATTERNS.get(event)
        if pattern is None:
            return
        key = (event, shape)
        self.total[key] += 1
        if pattern.match(msg):
            self.full[key] += 1
            self.dispatched[key] += 1
        elif event in FALLBACKS and FALLBACKS[event].match(msg):
            self.dispatched[key] += 1

    def read(self, path):
        try:
            with replay_open(path) as reader:
                for line in reader:
                    self.lines += 1
                    extracted = replay_extract(line.rstrip('\r\n'))
                    if extracted is None:
                        continue
                    shape, event, msg, continuation = extracted
                    if continuation:
                        if event in PATTERNS:
                            self.continuations += 1
                        continue
                    self.add(shape, event, msg)
        except (OSError, EOFError, zlib.error) as error:
            self.skipped.append((path, type(error).__name__))
            return
        self.files += 1


def replay_cell(matched, total):
    if not total:
        return 'no data'
    return f"{matched}/{total} {100.0 * matched / total:.1f}%"


def replay_report(counts, out):
    """Write the counts table and the verdict; return the exit status."""
    rows = []
    for event in PATTERNS:
        rows.append((event, counts.full))
        if event in FALLBACKS:
            rows.append((event + REPLAY_HEAD_SUFFIX, counts.dispatched))
    width = max(len(name) for name, _ in rows) + 2
    out.write(f"{'event':<{width}}" + ''.join(f"{shape:<{REPLAY_CELL_WIDTH}}" for shape in REPLAY_SHAPES)
              + "total\n")
    below, no_data = [], []
    for name, matched in rows:
        event = name[:-len(REPLAY_HEAD_SUFFIX)] if name.endswith(REPLAY_HEAD_SUFFIX) else name
        cells = [replay_cell(matched[(event, shape)], counts.total[(event, shape)]) for shape in REPLAY_SHAPES]
        all_matched = sum(matched[(event, shape)] for shape in REPLAY_SHAPES)
        all_total = sum(counts.total[(event, shape)] for shape in REPLAY_SHAPES)
        out.write(f"{name:<{width}}" + ''.join(f"{cell:<{REPLAY_CELL_WIDTH}}" for cell in cells)
                  + replay_cell(all_matched, all_total) + "\n")
        if name.endswith(REPLAY_HEAD_SUFFIX) or event not in FALLBACKS:
            dispatched = sum(counts.dispatched[(event, shape)] for shape in REPLAY_SHAPES)
            if not all_total:
                no_data.append(event)
            elif dispatched < all_total:
                below.append(event)
    out.write(f"files read: {counts.files}, lines read: {counts.lines}, "
              f"continuation lines skipped: {counts.continuations}\n")
    for path, error in counts.skipped:
        out.write(f"skipped {path}: {error}\n")
    out.write(f"no data: {', '.join(no_data) or 'none'}\n")
    out.write(f"below 100%: {', '.join(below) or 'none'}\n")
    return REPLAY_EXIT_BELOW if below else REPLAY_EXIT_OK


def replay_main(argv):
    if 'PATTERNS' not in globals() or 'split_frame' not in globals() or not argv:
        sys.stderr.write(REPLAY_USAGE)
        return REPLAY_EXIT_USAGE
    counts = ReplayCounts()
    for path in argv:
        counts.read(path)
    return replay_report(counts, sys.stdout)


if __name__ == '__main__':
    sys.exit(replay_main(sys.argv[1:]))

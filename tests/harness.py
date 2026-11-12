"""
Test harness: a temp DB built from prod's schema, a FIDO bot that records every line it sends,
and log capture. Synthetic data only: 192.0.2.0/24, 2001:db8::/32, the nick Jameson and
irc.example.test.

Import it as `from tests import harness` so every test module shares one copy.
"""
import collections
import contextlib
import logging
import os
import pathlib
import sqlite3
import tempfile

from sqlalchemy import create_engine

import fido
import models
from modules import sessiontracker
from modules.networkprotection import asn_blacklist

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'
PROD_SCHEMA = FIXTURES / 'prod_schema.sql'
# SQLite reserves this name and creates the table itself for AUTOINCREMENT tables.
RESERVED_STATEMENT = 'CREATE TABLE sqlite_sequence'

SERVER_NAME = 'irc.example.test'
BOT_NICK = 'FIDO[BOT]'
USER_NICK = 'Jameson'
USER_HOST = '192.0.2.10'
# UnrealIRCd's PREFIX=(qaohv)~&@%+
PREFIXES = collections.OrderedDict([('~', 'q'), ('&', 'a'), ('@', 'o'), ('%', 'h'), ('+', 'v')])


def schema_statements(path=PROD_SCHEMA) -> list:
    """The DDL statements in a schema file, minus the one SQLite reserves."""
    statements = []
    buffer = ''
    for line in pathlib.Path(path).read_text().splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ''
            if not statement.startswith(RESERVED_STATEMENT):
                statements.append(statement)
    if buffer.strip():
        raise ValueError(f"{path} ends with an incomplete statement")
    return statements


def reset_db_state():
    """Forget what modules keep in memory from the DB, so nothing carries over from one temp DB to the next."""
    asn_blacklist.forget_prefixes()
    sessiontracker.reset_purge_clock()


def build_db(path, schema=PROD_SCHEMA):
    """Create a SQLite file at path holding the schema's tables and indexes."""
    connection = sqlite3.connect(path)
    try:
        for statement in schema_statements(schema):
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


class TempDB:
    """
    A SQLite file in a temp dir, built from prod's schema (or empty with schema=False), that every
    models.session_scope() uses while the context is open.
    """

    def __init__(self, schema=True):
        self.schema = schema
        self.path = None
        self.url = None
        self.engine = None
        self._dir = None
        self._previous_engine = None

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._dir.name, 'FIDO.sqlite')
        if self.schema:
            build_db(self.path)
        self.url = f'sqlite:///{self.path}'
        self.engine = create_engine(self.url)
        self._previous_engine = models.engine
        models.use_engine(self.engine)
        reset_db_state()
        return self

    def __exit__(self, *exc):
        models.use_engine(self._previous_engine)
        reset_db_state()
        self.engine.dispose()
        self._dir.cleanup()
        return False

    def connect(self) -> sqlite3.Connection:
        """A second connection to the same file, independent of SQLAlchemy."""
        return sqlite3.connect(self.path)

    def table_names(self) -> set:
        with contextlib.closing(self.connect()) as connection:
            return {row[0] for row in connection.execute("select name from sqlite_master where type = 'table'")}

    def count(self, table: str) -> int:
        with contextlib.closing(self.connect()) as connection:
            return connection.execute(f'select count(*) from "{table}"').fetchone()[0]


class RecordingConnection:
    """Stands in for pydle's Connection and keeps every line sent, without the line ending."""

    def __init__(self, hostname=SERVER_NAME):
        self.hostname = hostname
        self.connected = True
        self.lines = []

    async def send(self, data: bytes):
        self.lines.extend(data.decode('utf-8').splitlines())

    async def disconnect(self):
        self.connected = False


class FakeBot(fido.FIDO):
    """
    A real FIDO, registered on irc.example.test without a socket. pydle formats every command as
    usual, so `lines` holds the exact wire lines (PRIVMSG, MODE, KICK, GLINE, MONITOR ...).
    WHOIS is answered from `whois_replies` (a missing nick gives None, as for 401).
    `receive(line)` runs a server line through pydle's parser and handlers. With `echo_joins` on,
    every JOIN FIDO sends is answered with the server's echo, as a real server does.
    Constructible without a running event loop.
    """

    def __init__(self, nickname=BOT_NICK):
        super().__init__(nickname)
        self.connection = RecordingConnection()
        self.encoding = 'utf-8'
        self.nickname = nickname
        self.registered = True
        self._isupport.update({'MONITOR': '128', 'WHOX': True})
        self._nickname_prefixes = PREFIXES.copy()
        self.whois_replies = {}
        self.echo_joins = False

    @property
    def lines(self) -> list:
        return self.connection.lines

    def messages(self, target=None) -> list:
        """(target, text) of every PRIVMSG sent, optionally only those to target."""
        sent = []
        for line in self.lines:
            command, _, rest = line.partition(' ')
            if command != 'PRIVMSG':
                continue
            to, _, text = rest.partition(' ')
            text = text[1:] if text.startswith(':') else text
            if target is None or self.is_same_channel(to, target):
                sent.append((to, text))
        return sent

    def add_channel(self, channel: str):
        if not self.in_channel(channel):
            self._create_channel(channel)
        return self.channels[channel]

    def add_user(self, nickname=USER_NICK, username='jameson', hostname=USER_HOST, channel=None,
                 status='', identified=False, oper=False, real_ip=None):
        """
        Put a user into pydle's user table, and into channel with the given status letters
        ('o', 'hv', ...) if a channel is named. The user answers WHOIS as pydle reports it, with
        'oper' from 313 and 'real_ip_address' from 378.
        """
        self.whois_replies[nickname] = {
            'oper': oper, 'idle': 0, 'away': False, 'away_message': None,
            'username': username, 'hostname': hostname, 'realname': nickname,
            'account': nickname if identified else None, 'identified': identified,
            'real_ip_address': real_ip, 'real_hostname': hostname if real_ip else None,
        }
        self.users[nickname] = {
            'nickname': nickname,
            'username': username,
            'realname': nickname,
            'hostname': hostname,
            'away': False,
            'away_message': None,
            'account': nickname if identified else None,
            'identified': identified,
        }
        if channel:
            modes = self.add_channel(channel)['modes']
            self.channels[channel]['users'].add(nickname)
            for letter in status:
                modes.setdefault(letter, []).append(nickname)
        return self.users[nickname]

    async def whois(self, nickname):
        return self.whois_replies.get(nickname)

    async def receive(self, line: str):
        """Handle one line from the server, as read from the socket, and wait for its handlers."""
        self._receive_buffer += (line + '\r\n').encode(self.encoding)
        while self._has_message():
            await self.on_raw(self._parse_message())

    async def join(self, channel, password=None):
        await super().join(channel, password)
        if self.echo_joins:
            await self.receive(f":{self.nickname}!fido@{SERVER_NAME} JOIN :{channel}")


class CaptureHandler(logging.Handler):
    """Keeps every record that reaches it."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def rendered(self) -> list:
        """Each record as the formatter writes it, exception text included."""
        return [self.format(record) for record in self.records]

    def messages(self) -> list:
        return [record.getMessage() for record in self.records]


@contextlib.contextmanager
def capture_logs(level=logging.DEBUG):
    """Capture every record that reaches the root logger at level or above."""
    root = logging.getLogger()
    handler = CaptureHandler()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(level)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


@contextlib.contextmanager
def preserved_root_logging():
    """Undo whatever logging.basicConfig() adds to the root logger inside the block."""
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    try:
        yield
    finally:
        for handler in list(root.handlers):
            if handler not in handlers:
                root.removeHandler(handler)
        root.setLevel(level)

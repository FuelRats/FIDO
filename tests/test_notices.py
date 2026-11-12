"""
The notice pipeline: the frame, the patterns, the origin guard in FIDO.on_notice, dispatch and the
unparsed warning, every handler, the gates, SMS through SNS (stubbed, no network) and the replay
tool. Fixtures: tests/fixtures/notices.txt. Synthetic data only.
"""
import asyncio
import collections
import contextlib
import gzip
import logging
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from botocore.stub import Stubber

from models import ircsessions, session_scope
from modules import configmanager, noticehandler, sms
from modules.notices import frame, patterns
from tests import harness

REPO = pathlib.Path(__file__).resolve().parent.parent
NOTICE_FIXTURES = harness.FIXTURES / 'notices.txt'
REPLAY_PARTS = [REPO / 'modules' / 'notices' / 'frame.py', REPO / 'modules' / 'notices' / 'patterns.py',
                REPO / 'tools' / 'replay_notices.py']
REPLAY_TIMEOUT = 60  # seconds
CUT_LENGTH = 585  # bytes, where long spamfilter hits were cut in the logs

BOT = harness.BOT_NICK
SERVER = harness.SERVER_NAME
OPERS = '#opers'
RATCHAT = '#ratchat'
STAFF = 'Jameson!jameson@staff.example.test'
TOPIC_ARN = 'arn:aws:sns:eu-central-1:123456789012:fido-sms-test'
# AWS's documented example key pair, so no credential lookup leaves the test process.
AWS_ENV = {'AWS_ACCESS_KEY_ID': 'AKIAIOSFODNN7EXAMPLE',
           'AWS_SECRET_ACCESS_KEY': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'}
OPS_REPLY = 'Your call for help has reached the ops'

RED, YELLOW, GREEN, RESET = '\x0304', '\x0308', '\x0303', '\x0f'


def load_fixtures(path=NOTICE_FIXTURES) -> dict:
    """name -> notice text, with each \\xNN escape turned into its byte."""
    fixtures = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        name, _, escaped = line.partition('\t')
        fixtures[name] = re.sub(r'\\x([0-9a-fA-F]{2})', lambda found: chr(int(found.group(1), 16)), escaped)
    return fixtures


NOTICES = load_fixtures()


def gline(mask, rest):
    return f"{RED}GLINE{RESET} {mask} was {rest}"


# name -> (event, a subset of the expected groups, expected PRIVMSGs, expected SMS text or None)
EXPECTED = {
    'gline_timed_id': ('tkl.TKL_ADD',
                       dict(type='G-Line', mask='*@192.0.2.10', reason='Spamming [repeat offender]', by=STAFF,
                            duration='1d12h', id='G1A2B3C4D5E6F'),
                       [(OPERS, gline('*@192.0.2.10', f"G-LINED by {STAFF} for 1d12h with message: "
                                                      f"Spamming [repeat offender]"))], None),
    'gline_timed_no_id': ('tkl.TKL_ADD',
                          dict(type='G-Line', mask='*@192.0.2.11', reason='Ban evasion', duration='7d', id=None),
                          [(OPERS, gline('*@192.0.2.11', f"G-LINED by {STAFF} for 7d with message: Ban evasion"))],
                          None),
    'gline_permanent_id': ('tkl.TKL_ADD',
                           dict(type='G-Line', mask='*@192.0.2.12', duration='permanent', id='G2B3C4D5E6F7A'),
                           [(OPERS, gline('*@192.0.2.12', f"PERMANENTLY G-LINED by {STAFF} with message: "
                                                          f"Network abuse"))], None),
    'gline_permanent_no_id': ('tkl.TKL_ADD',
                              dict(type='G-Line', mask='*@2001:db8::12', duration='permanent', id=None),
                              [(OPERS, gline('*@2001:db8::12', f"PERMANENTLY G-LINED by {STAFF} with message: "
                                                               f"Network abuse"))], None),
    'gline_by_fido': ('tkl.TKL_ADD', dict(type='G-Line', by='FIDO[BOT]!fido@bots.example.test', duration='7d'),
                      [], None),
    'soft_gline': ('tkl.TKL_ADD', dict(type='Soft G-Line', mask='%*@192.0.2.14', duration='2h'),
                   [(OPERS, gline('%*@192.0.2.14', f"G-LINED by {STAFF} for 2h with message: "
                                                   f"Please identify first"))], None),
    'shun_add': ('tkl.TKL_ADD', dict(type='Shun', mask='*@192.0.2.15'), [], None),
    'spamfilter_add': ('tkl.TKL_ADD', dict(type=None, sf='*badword*'), [], None),
    'kill': ('kill.KILL_COMMAND',
             dict(target='Jameson2!jameson@192.0.2.20', by='Jameson', reason='Spamming (third warning)'),
             [(OPERS, f"{RED}KILL{RESET} Jameson2 (192.0.2.20) was killed by Jameson with message: "
                      f"Spamming (third warning)")], None),
    'qline_626_unregistered': ('nick.QLINE_NICK_LOCAL_ATTEMPT',
                               dict(nick='ChanServ', client='[2001:db8::30]', ip=None,
                                    reason='Reserved for services (ID: Q1A2B3C4D5E6F)'),
                               [(OPERS, f"{RED}QLINE{RESET} ChanServ@2001:db8::30 refused connection: "
                                        f"Reserved for services (ID: Q1A2B3C4D5E6F)")], None),
    'qline_626_registered': ('nick.QLINE_NICK_LOCAL_ATTEMPT',
                             dict(nick='NickServ', client='Jameson!jameson@192.0.2.31', ip=None),
                             [(OPERS, f"{RED}QLINE{RESET} NickServ@192.0.2.31 refused connection: "
                                      f"Reserved for services")], None),
    'qline_606': ('nick.QLINE_NICK_LOCAL_ATTEMPT', dict(nick='OperServ', client=None, ip='192.0.2.32'),
                  [(OPERS, f"{RED}QLINE{RESET} OperServ@192.0.2.32 refused connection: Reserved for services")],
                  None),
    'oper_failed': ('oper.OPER_FAILED',
                    dict(client='Jameson!jameson@192.0.2.40', reason='Authentication failed', block='jameson'),
                    [(OPERS, f"Failed {RED}OPER{RESET} by Jameson (192.0.2.40): Authentication failed")], None),
    'spamfilter_ops_channel': ('tkl.SPAMFILTER_MATCH',
                               dict(nick='Jameson', user='jameson', host='192.0.2.50', filter='*opsignal*',
                                    cmd='PRIVMSG', target=RATCHAT, text='opsignal my client is stuck in the hangar',
                                    reason=OPS_REPLY, action='block'),
                               [(OPERS, f"OPS1GNAL by Jameson in {RATCHAT}: {OPS_REPLY}")],
                               f"OPSIGNAL by Jameson in {RATCHAT}: {OPS_REPLY}"),
    'spamfilter_ops_private': ('tkl.SPAMFILTER_MATCH',
                               dict(user='~jameson', filter='*OpsSignal*', target='Jameson2', action='block'),
                               [(OPERS, f"OPS1GNAL by Jameson in Jameson2: {OPS_REPLY}")],
                               f"OPSIGNAL by Jameson in Jameson2: {OPS_REPLY}"),
    'spamfilter_nick': ('tkl.SPAMFILTER_MATCH',
                        dict(filter='*badword*', cmd='NICK', target=None, text='Jameson_badword', action='block'),
                        [(OPERS, "SPAMFILTER Jameson -> NICK matched '*badword*' (block)")], None),
    'spamfilter_cut_585': ('tkl.SPAMFILTER_MATCH',
                           dict(nick='Jameson', host='192.0.2.54', filter='*opsignal*', cmd='PRIVMSG',
                                target=RATCHAT),
                           [(OPERS, f"OPS1GNAL by Jameson in {RATCHAT}")], f"OPSIGNAL by Jameson in {RATCHAT}"),
    'spamfilter_hidden_text': ('tkl.SPAMFILTER_MATCH',
                               dict(filter='*advert*', cmd='PRIVMSG', target=RATCHAT, text=None, action='kill'),
                               [(OPERS, f"SPAMFILTER Jameson -> {RATCHAT} matched '*advert*' (kill)")], None),
    'connect_local': ('connect.LOCAL_CLIENT_CONNECT',
                      dict(nick='Jameson-2', user='~jameson', host='192.0.2.60', ip='192.0.2.60'), [], None),
    'connect_remote': ('connect.REMOTE_CLIENT_CONNECT',
                       dict(nick='Jameson_3', user='jameson', host='host-61.example.test', ip='2001:db8::61'),
                       [], None),
    'link_unreliable': ('link.LINK_UNRELIABLE', dict(server='leaf.irc.example.test', seconds='30'),
                        [(OPERS, f"{YELLOW}LINK WARNING{RESET} Connection to leaf.irc.example.test is unstable "
                                 f"(no response for 30 seconds)."),
                         (RATCHAT, f"{YELLOW}LINK WARNING{RESET} Connection to leaf.irc.example.test is unstable "
                                   f"(no response for 30 seconds). A netsplit may occur soon.")], None),
    'link_lost_ipv4': ('link.LINK_DISCONNECTED',
                       dict(server='leaf.irc.example.test', ip='192.0.2.70', reason='Ping timeout: 120 seconds'),
                       [(OPERS, f"{RED}LINK DOWN{RESET} Lost server link to leaf.irc.example.test.")], None),
    'link_lost_ipv6': ('link.LINK_DISCONNECTED', dict(ip='2001:db8::70', reason='Connection reset by peer'),
                       [(OPERS, f"{RED}LINK DOWN{RESET} Lost server link to leaf.irc.example.test.")], None),
    'link_tls': ('link.SERVER_LINKED',
                 dict(src='hub.irc.example.test', dst='leaf.irc.example.test',
                      tls='TLSv1.3/TLS_CHACHA20_POLY1305_SHA256'),
                 [(OPERS, f"{GREEN}LINK RESTORED{RESET} Server link reestablished: "
                          f"hub.irc.example.test -> leaf.irc.example.test")], None),
    'link_plaintext': ('link.SERVER_LINKED', dict(dst='services.irc.example.test', tls=None),
                       [(OPERS, f"{GREEN}LINK RESTORED{RESET} Server link reestablished: "
                                f"hub.irc.example.test -> services.irc.example.test")], None),
}
# Fixtures whose connect notice stores a session: name -> (nick, stored hostmask)
SESSIONS = {'connect_local': ('Jameson-2', '192.0.2.60'), 'connect_remote': ('Jameson_3', '2001:db8::61')}


def framed(event, text, level='info'):
    return f"\x0314{event}\x0f \x0303[{level}]\x0f {text}"


def stored_sessions():
    with session_scope() as session:
        return [(row.nickname, row.hostmask) for row in session.query(ircsessions.IRCSessions)]


class FixtureTest(unittest.TestCase):
    def test_every_fixture_has_expectations(self):
        self.assertEqual(set(NOTICES), set(EXPECTED))

    def test_every_dispatched_event_has_a_pattern_and_a_fixture(self):
        self.assertEqual(set(noticehandler.HANDLERS), set(patterns.PATTERNS))
        self.assertEqual(set(patterns.PATTERNS), {event for event, *_ in EXPECTED.values()})

    def test_fixtures_are_coloured(self):
        for name, notice in NOTICES.items():
            with self.subTest(name):
                self.assertTrue(notice.startswith('\x0314'))
                self.assertNotEqual(frame.strip_formatting(notice), notice)

    def test_cut_spamfilter_hit_is_585_bytes_and_needs_the_fallback(self):
        notice = NOTICES['spamfilter_cut_585']
        self.assertEqual(len(notice.encode('utf-8')), CUT_LENGTH)
        text = frame.split_frame(frame.strip_formatting(notice)).group('msg')
        self.assertIsNone(patterns.PATTERNS['tkl.SPAMFILTER_MATCH'].match(text))
        self.assertIsNotNone(patterns.FALLBACKS['tkl.SPAMFILTER_MATCH'].match(text))


class FrameTest(unittest.TestCase):
    def test_strip_formatting(self):
        self.assertEqual(frame.strip_formatting('\x02bold\x02 \x0304,01red\x03 \x1fu\x1f \x1di\x1d \x16r\x16\x0f'),
                         'bold red u i r')

    def test_split_frame(self):
        found = frame.split_frame(frame.strip_formatting(NOTICES['link_lost_ipv4']))
        self.assertEqual(found.group('event'), 'link.LINK_DISCONNECTED')
        self.assertEqual(found.group('level'), 'error')
        self.assertEqual(found.group('cont'), '')
        self.assertTrue(found.group('msg').startswith('Lost server link to '))

    def test_continuation_marker(self):
        found = frame.split_frame('tkl.TKL_ADD+ [info] first line')
        self.assertEqual(found.group('cont'), frame.CONTINUATION)

    def test_unframed_text_is_not_a_frame(self):
        self.assertIsNone(frame.split_frame("[Spamfilter] Jameson!jameson@192.0.2.50 matches filter '*opsignal*'"))
        self.assertIsNone(frame.split_frame('*** Looking up your hostname...'))


class PatternTest(unittest.TestCase):
    def test_every_fixture_parses_to_the_expected_groups(self):
        for name, (event, groups, _, _) in EXPECTED.items():
            with self.subTest(name):
                found = frame.split_frame(frame.strip_formatting(NOTICES[name]))
                self.assertEqual(found.group('event'), event)
                match = patterns.match_notice(event, found.group('msg'))
                self.assertIsNotNone(match)
                self.assertEqual({key: match.groupdict().get(key) for key in groups}, groups)

    def test_unknown_event_has_no_match(self):
        self.assertIsNone(patterns.match_notice('tkl.TKL_EXPIRE', "Expiring G-Line '*@192.0.2.10'"))

    def test_patterns_are_built_from_the_sources(self):
        for event, source in patterns.PATTERN_SOURCES.items():
            self.assertEqual(patterns.PATTERNS[event].pattern, source)


class NoticeTestCase(unittest.IsolatedAsyncioTestCase):
    """A FakeBot on a temp DB, with SMS replaced by a recording mock."""

    def setUp(self):
        self.db = self.enterContext(harness.TempDB())
        self.bot = harness.FakeBot()
        self.send_sms = self.enterContext(mock.patch.object(sms, 'send_to_group', mock.AsyncMock(return_value=True)))
        self.enterContext(mock.patch.object(noticehandler, 'unparsed', collections.Counter()))
        self.enterContext(mock.patch.object(noticehandler, '_last_report', noticehandler.time.monotonic()))

    async def server_notice(self, name_or_text, target=BOT, by=SERVER):
        await self.bot.on_notice(target, by, NOTICES.get(name_or_text, name_or_text))

    def sms_texts(self):
        return [call.args for call in self.send_sms.await_args_list]

    def set_gate(self, gate, value):
        configmanager.set_config(*gate, value)


class HandlerTest(NoticeTestCase):
    async def test_every_fixture_gives_the_expected_messages(self):
        for name, (_, _, messages, sms_text) in EXPECTED.items():
            with self.subTest(name):
                with session_scope() as session:
                    session.query(ircsessions.IRCSessions).delete()
                bot = harness.FakeBot()
                self.send_sms.reset_mock()
                await bot.on_notice(BOT, SERVER, NOTICES[name])
                self.assertEqual(bot.messages(), messages)
                self.assertEqual(self.sms_texts(), [('ops', sms_text)] if sms_text else [])
                if name in SESSIONS:
                    self.assertEqual(stored_sessions(), [SESSIONS[name]])
            await asyncio.sleep(0)  # one loop step per fixture keeps asyncio's slow-step debug report quiet

    async def test_connect_uses_the_ip_not_the_hostname(self):
        await self.server_notice('connect_remote')
        self.assertEqual(stored_sessions(), [('Jameson_3', '2001:db8::61')])

    async def test_connect_without_an_ip_is_skipped_without_a_lookup(self):
        not_an_ip = 'host-80.example.test'
        notice = framed('connect.LOCAL_CLIENT_CONNECT',
                        f"Client connecting: Jameson-5 (jameson@{not_an_ip}) [{not_an_ip}] [class: clients]")
        with harness.capture_logs(logging.DEBUG) as logs:
            await self.server_notice(notice)
        warnings = [record.getMessage() for record in logs.records if record.levelno == logging.WARNING]
        self.assertEqual(len(warnings), 2)
        self.assertFalse(any(not_an_ip in text for text in warnings))
        self.assertEqual(stored_sessions(), [])
        self.assertEqual(self.bot.lines, [])

    async def test_second_nick_from_one_ip_is_reported_as_a_clone(self):
        await self.server_notice('connect_local')
        await self.server_notice(NOTICES['connect_local'].replace('Jameson-2', 'Jameson-4'))
        clone_reports = [text for _, text in self.bot.messages(OPERS) if 'CLONE' in text]
        self.assertEqual(len(clone_reports), 1)
        self.assertIn('Jameson-4 has connected from 192.0.2.60, previous nicknames: Jameson-2', clone_reports[0])

    async def test_continuation_line_is_skipped(self):
        notice = NOTICES['kill'].replace('kill.KILL_COMMAND', 'kill.KILL_COMMAND+', 1)
        with harness.capture_logs(logging.DEBUG) as logs:
            await self.server_notice(notice)
        self.assertEqual(self.bot.messages(), [])
        self.assertIn('Skipped a continuation line of kill.KILL_COMMAND', logs.messages())


class OriginGuardTest(NoticeTestCase):
    """The framed, coloured ops alert hit, sent by a user and by a server."""

    def setUp(self):
        super().setUp()
        self.handle = self.enterContext(mock.patch.object(
            noticehandler, 'handle_notice', mock.AsyncMock(wraps=noticehandler.handle_notice)))

    async def assert_ignored(self, target, by):
        await self.server_notice('spamfilter_ops_channel', target=target, by=by)
        self.handle.assert_not_awaited()
        self.assertEqual(self.bot.lines, [])
        self.send_sms.assert_not_awaited()

    async def test_notice_from_a_user_reaches_no_handler_and_no_sms(self):
        await self.assert_ignored(BOT, harness.USER_NICK)

    async def test_notice_from_a_server_reaches_the_handler_and_the_sms(self):
        await self.server_notice('spamfilter_ops_channel')
        self.handle.assert_awaited_once()
        self.assertEqual(self.bot.messages(), [(OPERS, f"OPS1GNAL by Jameson in {RATCHAT}: {OPS_REPLY}")])
        self.assertEqual(self.sms_texts(), [('ops', f"OPSIGNAL by Jameson in {RATCHAT}: {OPS_REPLY}")])

    async def test_server_notice_to_a_channel_is_ignored(self):
        await self.assert_ignored(OPERS, SERVER)

    async def test_server_notice_before_registration_is_ignored(self):
        await self.assert_ignored('*', SERVER)

    async def test_notice_without_a_source_is_ignored(self):
        await self.assert_ignored(BOT, None)

    async def test_target_matches_in_the_server_case_mapping(self):
        await self.server_notice('spamfilter_ops_channel', target='fido{bot}')
        self.handle.assert_awaited_once()


class GateTest(NoticeTestCase):
    OPER_REPORTS = ['gline_timed_id', 'kill', 'qline_606', 'oper_failed', 'spamfilter_nick',
                    'spamfilter_ops_channel', 'link_unreliable', 'link_lost_ipv4', 'link_tls']

    async def test_gates_default_to_on(self):
        for gate in (configmanager.GATE_OPERS_REPORTS, configmanager.GATE_SMS,
                     configmanager.GATE_RATCHAT_LINK_WARNINGS):
            self.assertTrue(configmanager.gate_open(gate))

    async def test_opers_reports_off_silences_the_oper_channel(self):
        self.set_gate(configmanager.GATE_OPERS_REPORTS, configmanager.FLAG_OFF)
        for name in self.OPER_REPORTS:
            await self.server_notice(name)
        self.assertEqual(self.bot.messages(OPERS), [])
        self.assertEqual([to for to, _ in self.bot.messages()], [RATCHAT])
        self.assertEqual(len(self.sms_texts()), 1)

    async def test_sms_off_keeps_the_oper_channel_line(self):
        self.set_gate(configmanager.GATE_SMS, configmanager.FLAG_OFF)
        await self.server_notice('spamfilter_ops_channel')
        self.assertEqual(self.bot.messages(), [(OPERS, f"OPS1GNAL by Jameson in {RATCHAT}: {OPS_REPLY}")])
        self.send_sms.assert_not_awaited()

    async def test_ratchat_link_warnings_off_keeps_the_oper_channel_warning(self):
        self.set_gate(configmanager.GATE_RATCHAT_LINK_WARNINGS, configmanager.FLAG_OFF)
        await self.server_notice('link_unreliable')
        self.assertEqual([to for to, _ in self.bot.messages()], [OPERS])

    async def test_every_gate_off_means_no_output(self):
        for gate in (configmanager.GATE_OPERS_REPORTS, configmanager.GATE_SMS,
                     configmanager.GATE_RATCHAT_LINK_WARNINGS):
            self.set_gate(gate, configmanager.FLAG_OFF)
        for name in self.OPER_REPORTS + ['spamfilter_cut_585', 'link_plaintext', 'qline_626_unregistered']:
            await self.server_notice(name)
        self.assertEqual(self.bot.lines, [])
        self.send_sms.assert_not_awaited()

    async def test_a_gate_change_by_another_connection_applies_to_the_next_notice(self):
        await self.server_notice('kill')
        with contextlib.closing(self.db.connect()) as connection:
            connection.execute("insert into config (module, key, value) values (?, ?, ?)",
                               (*configmanager.GATE_OPERS_REPORTS, configmanager.FLAG_OFF))
            connection.commit()
        await self.server_notice('kill')
        self.assertEqual(len(self.bot.messages(OPERS)), 1)


class UnparsedTest(NoticeTestCase):
    async def test_known_event_that_does_not_match_logs_a_warning_without_its_text(self):
        notice = framed('kill.KILL_COMMAND', 'Client removed: Jameson2!jameson@192.0.2.20')
        with harness.capture_logs(logging.DEBUG) as logs:
            await self.server_notice(notice)
        warnings = [record.getMessage() for record in logs.records if record.levelno == logging.WARNING]
        self.assertEqual(warnings, ['unparsed kill.KILL_COMMAND'])
        self.assertFalse(any('Jameson' in text or '192.0.2.20' in text for text in logs.rendered()))
        self.assertEqual(noticehandler.unparsed, {'kill.KILL_COMMAND': 1})
        self.assertEqual(self.bot.lines, [])

    async def test_event_without_a_handler_is_ignored(self):
        notice = framed('tkl.TKL_EXPIRE', "Expiring G-Line '*@192.0.2.10' [reason: Ban evasion]")
        with harness.capture_logs(logging.DEBUG) as logs:
            await self.server_notice(notice)
        self.assertFalse(any(record.levelno >= logging.WARNING for record in logs.records))
        self.assertEqual(noticehandler.unparsed, {})

    def test_hourly_summary_logs_the_counts_and_resets_them(self):
        noticehandler.unparsed.update({'kill.KILL_COMMAND': 2, 'tkl.TKL_ADD': 1})
        start = noticehandler._last_report
        with harness.capture_logs(logging.DEBUG) as logs:
            noticehandler.report_unparsed(now=start + noticehandler.UNPARSED_REPORT_INTERVAL - 1)
            self.assertEqual(logs.records, [])
            noticehandler.report_unparsed(now=start + noticehandler.UNPARSED_REPORT_INTERVAL)
        self.assertEqual(logs.messages(), ['unparsed notices in the last 60 minutes: kill.KILL_COMMAND 2, '
                                           'tkl.TKL_ADD 1'])
        self.assertEqual(logs.records[0].levelno, logging.WARNING)
        self.assertEqual(noticehandler.unparsed, {})

    def test_hourly_summary_is_silent_without_unparsed_notices(self):
        with harness.capture_logs(logging.DEBUG) as logs:
            noticehandler.report_unparsed(now=noticehandler._last_report + noticehandler.UNPARSED_REPORT_INTERVAL)
        self.assertEqual(logs.records, [])


class SMSTest(unittest.IsolatedAsyncioTestCase):
    TEXT = f"OPSIGNAL by Jameson in {RATCHAT}: {OPS_REPLY}"
    MESSAGE_ID = '6f1c2a9e-3b4d-5e6f-8a9b-0c1d2e3f4a5b'

    def setUp(self):
        self.db = self.enterContext(harness.TempDB())
        self.enterContext(mock.patch.dict(os.environ, AWS_ENV))
        self.enterContext(mock.patch.object(sms, '_client', None))

    def stubber(self) -> Stubber:
        return self.enterContext(Stubber(sms.client()))

    def test_client_settings(self):
        client = sms.client()
        self.assertEqual(client.meta.region_name, 'eu-central-1')
        self.assertEqual(client.meta.config.connect_timeout, 5)
        self.assertEqual(client.meta.config.read_timeout, 10)
        # botocore counts the first try too: 2 retries are 3 attempts.
        self.assertEqual(client.meta.config.retries['total_max_attempts'], 3)
        self.assertIs(sms.client(), client)

    async def test_publishes_to_the_group_topic(self):
        configmanager.set_config('sms', 'topic/ops', TOPIC_ARN)
        stubber = self.stubber()
        stubber.add_response('publish', {'MessageId': self.MESSAGE_ID}, {'TopicArn': TOPIC_ARN, 'Message': self.TEXT})
        with harness.capture_logs(logging.INFO) as logs:
            self.assertTrue(await sms.send_to_group('ops', self.TEXT))
        stubber.assert_no_pending_responses()
        self.assertIn(f"SMS to group ops published, message id {self.MESSAGE_ID}", logs.messages())

    async def test_missing_topic_warns_and_sends_nothing(self):
        with mock.patch.object(sms, 'client') as client, harness.capture_logs(logging.DEBUG) as logs:
            self.assertFalse(await sms.send_to_group('ops', self.TEXT))
        client.assert_not_called()
        warnings = [record.getMessage() for record in logs.records if record.levelno == logging.WARNING]
        self.assertEqual(len(warnings), 1)
        self.assertIn('sms/topic/ops', warnings[0])

    async def test_failed_publish_is_logged_and_returns_false(self):
        configmanager.set_config('sms', 'topic/ops', TOPIC_ARN)
        stubber = self.stubber()
        stubber.add_client_error('publish', service_error_code='AuthorizationError',
                                 service_message='Not authorized', http_status_code=403)
        with harness.capture_logs(logging.DEBUG) as logs:
            self.assertFalse(await sms.send_to_group('ops', self.TEXT))
        errors = [record.getMessage() for record in logs.records if record.levelno == logging.ERROR]
        self.assertEqual(len(errors), 1)
        self.assertIn('SMS to group ops failed', errors[0])


class ReplayTest(unittest.TestCase):
    """tools/replay_notices.py, concatenated after frame.py and patterns.py as it is shipped."""

    def setUp(self):
        self.dir = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.script = b''.join(part.read_bytes() for part in REPLAY_PARTS)

    def run_replay(self, *paths, script=None):
        return subprocess.run([sys.executable, '-I', '-', *map(str, paths)], input=script or self.script,
                              capture_output=True, timeout=REPLAY_TIMEOUT, cwd=self.dir)

    @staticmethod
    def fido_line(notice, source=SERVER):
        return f"DEBUG:FIDO:127.0.0.1:<< @msgid=Qx7Lm2;time=2026-11-12T10:00:00.000Z :{source} NOTICE {BOT} :{notice}\n"

    @staticmethod
    def ircd_line(event, level, text):
        return f"[2026-11-12T10:00:00.000Z] {SERVER} {event} {level}: {text}\n"

    def fido_log(self) -> str:
        lines = [f"DEBUG:FIDO:127.0.0.1:>> PRIVMSG {OPERS} :status\n", "INFO:fido:Connected!\n"]
        lines += [self.fido_line(notice) for notice in NOTICES.values()]
        # A framed line from a user, and a continuation line: neither is counted.
        lines.append(self.fido_line(NOTICES['spamfilter_ops_channel'], source='Jameson!jameson@192.0.2.10'))
        lines.append(self.fido_line(NOTICES['kill'].replace('kill.KILL_COMMAND', 'kill.KILL_COMMAND+', 1)))
        return ''.join(lines)

    def ircd_log(self) -> str:
        text = {name: frame.split_frame(frame.strip_formatting(NOTICES[name])).group('msg')
                for name in ('kill', 'spamfilter_ops_channel', 'spamfilter_cut_585')}
        return (self.ircd_line('kill.KILL_COMMAND', 'info', text['kill'])
                + self.ircd_line('tkl.SPAMFILTER_MATCH', 'info', text['spamfilter_ops_channel'])
                + self.ircd_line('tkl.SPAMFILTER_MATCH', 'info', text['spamfilter_cut_585'])
                + "[2026-11-12T10:00:01.000Z] irc.example.test connect.LOCAL_CLIENT_DISCONNECT info: "
                  "Client exiting: Jameson (jameson@192.0.2.10) [192.0.2.10] (Quit: bye)\n")

    def write_logs(self):
        plain = self.dir / 'fido.log'
        plain.write_text(self.fido_log(), encoding='utf-8')
        packed = self.dir / 'fido.log.1.gz'
        with gzip.open(packed, 'wt', encoding='utf-8') as writer:
            writer.write(self.fido_log())
        ircd = self.dir / 'ircd.log'
        ircd.write_text(self.ircd_log(), encoding='utf-8')
        return plain, packed, ircd

    @staticmethod
    def rows(stdout: str) -> dict:
        """event row name -> its cells (fido.log, ircd.log, total)."""
        rows = {}
        for line in stdout.splitlines():
            name = line.split(' ', 1)[0]
            cells = re.findall(r'\d+/\d+ [\d.]+%|no data', line)
            if cells:
                rows[name + (' head' if ' head ' in line else '')] = cells
        return rows

    def test_counts_per_event_and_source(self):
        result = self.run_replay(*self.write_logs(), self.dir / 'ircd.log.old')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        stdout = result.stdout.decode()
        rows = self.rows(stdout)
        per_file = collections.Counter(event for event, *_ in EXPECTED.values())
        for event in patterns.PATTERNS:
            if event in ('kill.KILL_COMMAND', 'tkl.SPAMFILTER_MATCH'):
                continue
            count = 2 * per_file[event]
            with self.subTest(event):
                self.assertEqual(rows[event], [f"{count}/{count} 100.0%", 'no data', f"{count}/{count} 100.0%"])
        self.assertEqual(rows['kill.KILL_COMMAND'], ['2/2 100.0%', '1/1 100.0%', '3/3 100.0%'])
        spamfilter = 2 * per_file['tkl.SPAMFILTER_MATCH']
        self.assertEqual(rows['tkl.SPAMFILTER_MATCH'],
                         [f"{spamfilter - 2}/{spamfilter} {100 * (spamfilter - 2) / spamfilter:.1f}%",
                          '1/2 50.0%', f"{spamfilter - 1}/{spamfilter + 2} "
                                       f"{100 * (spamfilter - 1) / (spamfilter + 2):.1f}%"])
        self.assertEqual(rows['tkl.SPAMFILTER_MATCH head'],
                         [f"{spamfilter}/{spamfilter} 100.0%", '2/2 100.0%',
                          f"{spamfilter + 2}/{spamfilter + 2} 100.0%"])
        self.assertIn('continuation lines skipped: 2', stdout)
        self.assertIn('files read: 3,', stdout)
        self.assertIn(f"skipped {self.dir / 'ircd.log.old'}: FileNotFoundError", stdout)
        self.assertIn('below 100%: none', stdout)
        self.assertIn('no data: none', stdout)

    def test_prints_no_line_content(self):
        result = self.run_replay(*self.write_logs())
        stdout = result.stdout.decode()
        for fragment in ('192.0.2', '2001:db8', 'Jameson', 'example.test', 'Spamming', 'opsignal'):
            self.assertNotIn(fragment, stdout)
        self.assertEqual(result.stderr, b'')

    def test_events_without_lines_are_no_data(self):
        log = self.dir / 'ircd.log'
        log.write_text(self.ircd_log(), encoding='utf-8')
        result = self.run_replay(log)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        rows = self.rows(result.stdout.decode())
        self.assertEqual(rows['tkl.TKL_ADD'], ['no data', 'no data', 'no data'])
        no_data = [line for line in result.stdout.decode().splitlines() if line.startswith('no data:')][0]
        self.assertIn('tkl.TKL_ADD', no_data)
        self.assertNotIn('kill.KILL_COMMAND', no_data)

    def test_a_miss_is_reported_and_fails(self):
        log = self.dir / 'ircd.log'
        log.write_text(self.ircd_log() + self.ircd_line('kill.KILL_COMMAND', 'info', 'Client removed: Jameson2'),
                       encoding='utf-8')
        result = self.run_replay(log)
        self.assertEqual(result.returncode, 1)
        stdout = result.stdout.decode()
        self.assertEqual(self.rows(stdout)['kill.KILL_COMMAND'], ['no data', '1/2 50.0%', '1/2 50.0%'])
        self.assertIn('below 100%: kill.KILL_COMMAND', stdout)

    def test_refuses_to_run_without_frame_and_patterns(self):
        log = self.dir / 'ircd.log'
        log.write_text(self.ircd_log(), encoding='utf-8')
        result = self.run_replay(log, script=REPLAY_PARTS[2].read_bytes())
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'usage:', result.stderr)

    def test_refuses_to_run_without_paths(self):
        self.assertEqual(self.run_replay().returncode, 2)

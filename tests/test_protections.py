"""
Channel protections, the DNSBL lockdown, the #NewRats greeting, the session tracker and the ASN
prefix cache, on the fake bot with a temp DB from prod's schema. Synthetic data only.
"""
import asyncio
import datetime
import logging
import unicodedata
import unittest
from unittest import mock

from tests import harness
from models import asn_blacklist, config, ircsessions, monitor, session_scope
from modules import access, configmanager, sessiontracker
from modules.channelprotections import droneprotection, masshighlighting, spamprotection, zalgoprotection
from modules.networkprotection import asn_blacklist as asn_protection
from modules.newrats import induction
from modules.notices import connect, patterns

BOT = harness.BOT_NICK
SERVER = harness.SERVER_NAME
SENDER = harness.USER_NICK
HOST = harness.USER_HOST
RATCHAT = '#ratchat'
OPERS = '#opers'
LOCKDOWN_BAN = '~forward:#NewRats:~security-group:unknown-users'

ZALGO_MARKS = ''.join(chr(code) for code in (0x300, 0x301, 0x302, 0x303, 0x304))
ZALGO = ' '.join(''.join(letter + ZALGO_MARKS for letter in word) for word in 'please help me'.split())
ACCENTED = {
    # "A loaf of bread here is very tasty": the per-word mark share alone (without the stacking rule) flags it.
    'vietnamese': 'Ở đây có ổ bánh mì ngon lắm',
    'vietnamese_long': 'Tiếng Việt có dấu thanh và dấu mũ trên nhiều chữ cái',
    'french': 'Ça a été très agréable, à bientôt à Noël et joyeuses fêtes',
    'polish': 'Zażółć gęślą jaźń, to jest zdanie z polskimi znakami',
}


def now():
    return datetime.datetime.now()


def mark_share_percentile(text: str) -> float:
    """The 75th-percentile share of combining marks per word, without the stacking rule."""
    scores = []
    for word in unicodedata.normalize('NFD', text).split():
        categories = [unicodedata.category(c) for c in word]
        scores.append(sum(categories.count(c) for c in zalgoprotection.ZALGO_CHAR_CATEGORIES) / len(word))
    return zalgoprotection.percentile(scores)


class ProtectionTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = self.enterContext(harness.TempDB())
        self.bot = harness.FakeBot()

    def kicks(self):
        return [line for line in self.bot.lines if line.startswith('KICK ')]


class ZalgoTest(ProtectionTestCase):
    def test_accented_sentences_pass(self):
        for name, text in ACCENTED.items():
            with self.subTest(name):
                self.assertFalse(zalgoprotection.is_zalgo(unicodedata.normalize('NFD', text)))

    def test_the_stacking_rule_is_what_lets_vietnamese_pass(self):
        self.assertGreater(mark_share_percentile(ACCENTED['vietnamese']), zalgoprotection.THRESHOLD)

    async def test_zalgo_sample_is_kicked_with_its_reason(self):
        self.bot.add_user(SENDER, channel=RATCHAT)
        configmanager.set_config('channelprotection', 'reason_zalgo', 'Zalgo text is not allowed.')
        for text in ACCENTED.values():
            await zalgoprotection.on_message(self.bot, RATCHAT, SENDER, text)
        self.assertEqual(self.bot.lines, [])
        await zalgoprotection.on_message(self.bot, RATCHAT, SENDER, ZALGO)
        self.assertEqual(self.kicks(), [f'KICK {RATCHAT} {SENDER} :Zalgo text is not allowed.'])
        self.assertEqual(self.bot.messages(OPERS), [(OPERS, f'{SENDER} was kicked from channel {RATCHAT} for using zalgo.')])

    async def test_zalgo_falls_back_to_the_common_reason(self):
        self.bot.add_user(SENDER, channel=RATCHAT)
        await zalgoprotection.on_message(self.bot, RATCHAT, SENDER, ZALGO)
        self.assertEqual(self.kicks(), [f'KICK {RATCHAT} {SENDER} :{configmanager.DEFAULT_KICK_REASON}'])

    async def test_channel_action_reaches_the_protections_private_action_does_not(self):
        self.bot.add_user(SENDER, channel=RATCHAT)
        with harness.capture_logs(logging.ERROR) as logs:
            await self.bot.receive(f':{SENDER}!jameson@{HOST} PRIVMSG {BOT} :\x01ACTION {ZALGO}\x01')
        self.assertEqual(self.bot.lines, [])
        self.assertEqual(logs.records, [])
        await self.bot.receive(f':{SENDER}!jameson@{HOST} PRIVMSG {RATCHAT} :\x01ACTION {ZALGO}\x01')
        self.assertEqual(len(self.kicks()), 1)


class FloodTest(ProtectionTestCase):
    def setUp(self):
        super().setUp()
        configmanager.set_config('channelprotection', 'messageinterval', '60')

    async def flood(self, nick, count=6):
        for _ in range(count):
            await spamprotection.on_message(self.bot, RATCHAT, nick, 'hello')
            await asyncio.sleep(0)  # one loop step per message keeps asyncio's slow-step debug report quiet

    async def test_half_op_is_exempt(self):
        self.bot.add_user(SENDER, channel=RATCHAT, status='h')
        await self.flood(SENDER)
        self.assertEqual(self.bot.lines, [])
        self.assertEqual(self.db.count('messagecounter'), 0)

    async def test_voice_is_kicked_with_the_flood_reason(self):
        self.bot.add_user(SENDER, channel=RATCHAT, status='v')
        configmanager.set_config('channelprotection', 'reason_flood', 'Slow down, please.')
        await self.flood(SENDER)
        self.assertEqual(self.kicks(), [f'KICK {RATCHAT} {SENDER} :Slow down, please.'])

    async def test_string_valued_channel_modes_are_ignored(self):
        # pydle keeps parameter modes (+k key, +H history, +f flood) as strings; the nick is a substring of the key.
        self.bot.add_user(SENDER, channel=RATCHAT, status='v')
        modes = self.bot.channels[RATCHAT]['modes']
        modes.update({'k': f'{SENDER}-key', 'H': '15:1440m', 'b': ['*!*@192.0.2.15'], 'n': True})
        self.assertEqual(access.get_access_level(self.bot, RATCHAT, SENDER), access.Levels.VOICE)
        await self.flood(SENDER, count=1)
        self.assertEqual(self.db.count('messagecounter'), 1)


class HighlightTest(ProtectionTestCase):
    async def test_highlight_kick_uses_its_reason(self):
        self.bot.add_user(SENDER, channel=RATCHAT)
        bystanders = [f'{SENDER}{n}' for n in range(2, 7)]
        for nick in bystanders:
            self.bot.add_user(nick, hostname='192.0.2.20', channel=RATCHAT)
        configmanager.set_config('channelprotection', 'reason_highlight', 'Please do not mass highlight.')
        await masshighlighting.on_message(self.bot, RATCHAT, SENDER, ' '.join(bystanders))
        self.assertEqual(self.kicks(), [f'KICK {RATCHAT} {SENDER} :Please do not mass highlight.'])


class UntrackedChannelTest(ProtectionTestCase):
    """A channel missing from bot.channels is skipped with a DEBUG line, never a KeyError."""

    CHANNEL = '#rat-ops'

    async def test_protections_skip_a_channel_without_state(self):
        configmanager.set_config('channelprotection', 'messageinterval', '60')
        self.bot.add_user(SENDER)
        with harness.capture_logs(logging.DEBUG) as logs:
            for _ in range(6):
                await self.bot.receive(f':{SENDER}!jameson@{HOST} PRIVMSG {self.CHANNEL} :{ZALGO}')
        self.assertEqual(self.bot.lines, [])
        self.assertEqual([record.getMessage() for record in logs.records if record.levelno >= logging.WARNING], [])
        prefix = f'{self.CHANNEL} is not tracked'
        skipped = [record.getMessage() for record in logs.records
                   if record.levelno == logging.DEBUG and record.getMessage().startswith(prefix)]
        self.assertTrue(any('mass highlight' in message for message in skipped), skipped)
        self.assertTrue(any('flood' in message for message in skipped), skipped)
        self.assertTrue(any('zalgo' in message for message in skipped), skipped)
        self.assertEqual(self.db.count('messagecounter'), 0)

    def test_access_level_in_a_channel_without_state_is_none(self):
        with harness.capture_logs(logging.DEBUG) as logs:
            level = access.get_access_level(self.bot, self.CHANNEL, SENDER)
        self.assertEqual(level, access.Levels.NONE)
        self.assertEqual([(record.levelno, record.getMessage()) for record in logs.records],
                         [(logging.DEBUG, f'{self.CHANNEL} is not tracked: access level of {SENDER} taken as none')])


class DroneTest(ProtectionTestCase):
    REPORTER = 'Jameson2'  # an IRC operator

    def setUp(self):
        super().setUp()
        self.bot.add_user(self.REPORTER, hostname='192.0.2.11', channel=OPERS, oper=True)

    def report(self, n, ip=None):
        ip = f'192.0.2.{n}' if ip is None else ip
        return (f'DNSBL -> Jameson{n}!jameson@192.0.2.{n} [{ip}] appears in BL zone dnsbl.example.test '
                f'(open proxy)')

    async def drones(self, count, sender=REPORTER):
        for n in range(1, count + 1):
            await droneprotection.on_message(self.bot, OPERS, sender, self.report(n))
            await asyncio.sleep(0)  # one loop step per report keeps asyncio's slow-step debug report quiet

    def lockdown_rows(self):
        with session_scope() as session:
            return [row.value for row in session.query(config.Config).filter_by(module='droneprotection',
                                                                                key='lockdown')]

    async def test_missing_lockdown_row_means_off(self):
        await self.drones(1)
        self.assertEqual(self.db.count('drones'), 1)
        self.assertEqual(self.bot.lines, [])

    async def test_too_many_drones_start_a_lockdown(self):
        with harness.capture_logs(logging.WARNING) as logs:
            await self.drones(4)
        self.assertEqual(logs.messages(), ['LOCKDOWN!'])
        modes = [line for line in self.bot.lines if line.startswith('MODE ')]
        self.assertEqual(modes, [f'MODE {RATCHAT} +b {LOCKDOWN_BAN}', 'MODE #NewRats -i'])
        self.assertEqual(self.lockdown_rows(), ['True'])
        announcements = [text for _, text in self.bot.messages()]
        self.assertTrue(all('KILL' not in text for text in announcements), announcements)
        self.assertTrue(any('G-Lined' in text for text in announcements), announcements)
        self.assertFalse(any(line.startswith('GLINE') for line in self.bot.lines))
        self.bot.lines.clear()
        await droneprotection.on_message(self.bot, OPERS, 'Jameson2', self.report(9))
        self.assertIn('GLINE *@192.0.2.9 7d Connecting through a VPN or open proxy is not currently allowed.',
                      self.bot.lines)

    async def test_gate_off_means_no_lockdown_and_no_gline(self):
        configmanager.set_config(*configmanager.GATE_AUTO_LOCKDOWN, 'off')
        with harness.capture_logs(logging.INFO):
            await self.drones(4)
        self.assertEqual(self.bot.lines, [])
        self.assertEqual(self.lockdown_rows(), [])
        configmanager.set_config('droneprotection', 'lockdown', 'True')
        await self.drones(1)
        self.assertEqual(self.bot.lines, [])
        self.assertEqual(self.db.count('drones'), 5)

    async def test_reports_from_a_user_who_is_no_irc_operator_are_ignored(self):
        self.bot.add_user(SENDER, channel=OPERS)
        with harness.capture_logs(logging.INFO):
            await self.drones(4, sender=SENDER)
            configmanager.set_config('droneprotection', 'lockdown', 'True')
            await self.drones(1, sender=SENDER)
        self.assertEqual(self.bot.lines, [])
        self.assertEqual(self.db.count('drones'), 0)
        self.assertEqual(self.lockdown_rows(), ['True'])

    async def test_a_report_must_start_the_message(self):
        with harness.capture_logs(logging.INFO):
            for n in range(1, 5):
                await droneprotection.on_message(self.bot, OPERS, self.REPORTER, f'lol {self.report(n)}')
        self.assertEqual(self.bot.lines, [])
        self.assertEqual(self.db.count('drones'), 0)

    async def test_an_address_that_is_no_ip_address_is_not_glined(self):
        configmanager.set_config('droneprotection', 'lockdown', 'True')
        with harness.capture_logs(logging.INFO):
            for ip in ('', 'example.test', '192.0.2.300', '-'):
                await droneprotection.on_message(self.bot, OPERS, self.REPORTER, self.report(5, ip=ip))
        self.assertFalse(any(line.startswith('GLINE') for line in self.bot.lines), self.bot.lines)
        await droneprotection.on_message(self.bot, OPERS, self.REPORTER, self.report(6, ip='2001:db8::6'))
        self.assertIn('GLINE *@2001:db8::6 7d Connecting through a VPN or open proxy is not currently allowed.',
                      self.bot.lines)


class GreetingTest(ProtectionTestCase):
    GREETING = [
        'PRIVMSG #newrats :Jameson: Welcome to the Fuel Rats! If you are on emergency oxygen please log out to main '
        'menu.  If you need fuel, please let us know as soon as possible.  If you are interested in joining the '
        "cause, check out: https://t.fuelr.at/join .  If you're already a rat, or are a new recruit, please "
        'identify using the information below.',
        'PRIVMSG #newrats :Switch to the FuelRats tab in the top left corner (Or your Status window) and identify '
        'with NickServ with the following command, but replace <password> with your password: /msg NickServ '
        'IDENTIFY <password>',
    ]

    def setUp(self):
        super().setUp()
        self.bot.add_channel('#newrats')

    async def join(self, nick=SENDER, channel='#newrats'):
        await self.bot.receive(f':{nick}!jameson@{HOST} JOIN :{channel}')

    async def test_greeting_on_newrats(self):
        self.bot.add_user(SENDER)
        await self.join()
        self.assertEqual(self.bot.lines, self.GREETING)

    async def test_greeted_once_a_day(self):
        self.bot.add_user(SENDER)
        await self.join()
        await self.join(nick=SENDER.upper())
        self.assertEqual(len(self.bot.lines), 2)
        later = induction.time.monotonic() + induction.GREETING_MEMORY
        with mock.patch.object(induction, 'time', mock.Mock(monotonic=mock.Mock(return_value=later))):
            await self.join()
        self.assertEqual(len(self.bot.lines), 4)
        self.assertEqual(list(self.bot.recent_greeting), [self.bot.normalize(SENDER)])

    async def test_identified_users_and_gone_users_are_not_greeted(self):
        self.bot.add_user(SENDER, identified=True)
        await self.join()
        await self.join(nick='Jameson9')  # no WHOIS reply: gone already
        self.assertEqual(self.bot.lines, [])

    async def test_identified_and_gone_users_are_not_remembered_as_greeted(self):
        self.bot.add_user(SENDER, identified=True)
        await self.join()
        await self.join(nick='Jameson9')
        self.assertEqual(self.bot.recent_greeting, {})
        self.bot.add_user(SENDER, identified=False)  # logged out of services since
        await self.join()
        self.assertEqual(self.bot.lines, self.GREETING)

    async def test_joins_while_one_whois_is_pending_get_one_greeting(self):
        self.bot.add_user(SENDER)
        pending = asyncio.get_running_loop().create_future()
        asked = []
        send = self.bot.message

        async def shared_whois(nickname):
            """pydle answers every WHOIS of one nick sent before the reply with the same future."""
            asked.append(nickname)
            return await pending

        async def yielding_message(target, message):
            """A message whose write suspends once, as a write to a real socket can."""
            await asyncio.sleep(0)
            await send(target, message)

        with mock.patch.object(self.bot, 'whois', side_effect=shared_whois), \
                mock.patch.object(self.bot, 'message', side_effect=yielding_message):
            joins = [asyncio.create_task(self.join()) for _ in range(3)]
            async with asyncio.timeout(harness.WAIT_TIMEOUT):
                while len(asked) + sum(join.done() for join in joins) < len(joins):
                    await asyncio.sleep(0)
            pending.set_result(self.bot.whois_replies[SENDER])
            await asyncio.gather(*joins)
        self.assertEqual(self.bot.lines, self.GREETING)

    async def test_other_channels_and_gate_off(self):
        self.bot.add_user(SENDER)
        self.bot.add_channel(RATCHAT)
        await self.join(channel=RATCHAT)
        configmanager.set_config(*configmanager.GATE_NEWRATS_GREETING, 'off')
        await self.join()
        self.assertEqual(self.bot.lines, [])


class SessionTrackerTest(ProtectionTestCase):
    def add_session(self, nick, host, age):
        with session_scope() as session:
            session.add(ircsessions.IRCSessions(timestamp=now() - age, nickname=nick, hostmask=host,
                                                network='192.0.2.0/24'))

    def sessions(self):
        with session_scope() as session:
            return sorted((row.nickname, row.hostmask) for row in session.query(ircsessions.IRCSessions))

    def test_every_clone_is_collected_newest_time_last(self):
        hour = datetime.timedelta(hours=1)
        self.add_session('Jameson3', HOST, 3 * hour)
        self.add_session(SENDER, '192.0.2.99', 2 * hour)
        self.add_session('Jameson2', HOST, 1 * hour)
        clones, lasttime = sessiontracker.is_clone(SENDER, HOST, True)
        self.assertEqual(clones, ['Jameson3', 'Jameson2'])
        self.assertAlmostEqual(lasttime, now() - hour, delta=datetime.timedelta(seconds=5))
        self.assertEqual(sessiontracker.is_clone(SENDER, '192.0.2.98'), None)

    def test_known_pair_still_reports_its_clones_and_is_not_stored_twice(self):
        self.add_session(SENDER, HOST, datetime.timedelta(days=1))
        self.add_session('Jameson2', HOST, datetime.timedelta(hours=1))
        self.assertEqual(sessiontracker.is_clone(SENDER, HOST), ['Jameson2'])
        self.assertEqual(self.sessions(), [(SENDER, HOST), ('Jameson2', HOST)])

    def test_purge_runs_once_per_hour(self):
        retention = datetime.timedelta(days=sessiontracker.SessionHandler.retention_time + 1)
        self.add_session('Jameson3', '192.0.2.30', retention)
        sessiontracker.is_clone(SENDER, HOST)
        self.assertEqual(self.sessions(), [(SENDER, HOST)])
        self.add_session('Jameson3', '192.0.2.30', retention)
        sessiontracker.is_clone('Jameson2', '192.0.2.31')
        self.assertIn(('Jameson3', '192.0.2.30'), self.sessions())
        later = sessiontracker.time.monotonic() + sessiontracker.PURGE_INTERVAL
        with mock.patch.object(sessiontracker, 'time', mock.Mock(monotonic=mock.Mock(return_value=later))):
            sessiontracker.is_clone('Jameson2', '192.0.2.31')
        self.assertNotIn(('Jameson3', '192.0.2.30'), self.sessions())

    async def test_monitored_nick_is_reported_and_the_connect_checks_go_on(self):
        configmanager.set_config('channels', 'ratops', '#rat-ops-test')
        configmanager.set_config('channels', 'operchannel', '#opers-test')
        with session_scope() as session:
            session.add(monitor.Monitor(timestamp=now(), nickname='Jameson2', msg='Reason: ban evasion (Jameson4)'))
            session.add(asn_blacklist.ASNBlacklist(timestamp=now(), asn='AS64496', prefix='192.0.2.0', cidr='24',
                                                   reason='test', asn_name='EXAMPLE-NET'))
        self.add_session('Jameson2', HOST, datetime.timedelta(hours=1))
        notice = f'Client connecting: Jameson2 (jameson@{HOST}) [{HOST}] [class: clients]'
        match = patterns.match_notice('connect.LOCAL_CLIENT_CONNECT', notice)
        await connect.on_connect(self.bot, notice, match)
        await sessiontracker.check_clone(self.bot, SENDER, HOST)
        self.assertEqual(self.bot.messages(), [
            ('#rat-ops-test', 'Monitored nick Jameson2 has come online. (Reason: ban evasion (Jameson4))'),
            ('#opers', 'ASN BAN: User Jameson2 connecting from banned network AS64496: EXAMPLE-NET (192.0.2.0/24)'),
            ('#rat-ops-test', f'\x0304MONITOR\x0f Nick {SENDER} is a clone of monitored nick Jameson2!'),
            ('#opers-test', f'\x0304CLONE\x0f {SENDER} has connected from {HOST}, previous nicknames: Jameson2 '
                            f'(Last connected {self.last_connected("Jameson2")})'),
        ])

    def last_connected(self, nick):
        with session_scope() as session:
            return session.query(ircsessions.IRCSessions).filter_by(nickname=nick).one().timestamp


class ASNCacheTest(ProtectionTestCase):
    def add_ban(self, prefix, cidr):
        with session_scope() as session:
            session.add(asn_blacklist.ASNBlacklist(timestamp=now(), asn='AS64496', prefix=prefix, cidr=cidr,
                                                   reason='test', asn_name='EXAMPLE-NET'))

    def test_prefixes_are_read_once(self):
        self.add_ban('192.0.2.0', '25')
        with mock.patch.object(asn_protection, 'load_prefixes', wraps=asn_protection.load_prefixes) as load:
            self.assertIsNotNone(asn_protection.check_ban('192.0.2.200'))  # widened to 192.0.2.0/24
            self.assertIsNone(asn_protection.check_ban('2001:db8::1'))
            self.assertEqual(load.call_count, 1)
            self.add_ban('2001:db8::', '48')
            self.assertIsNone(asn_protection.check_ban('2001:db8::1'))
            asn_protection.reload_prefixes()
            self.assertIsNotNone(asn_protection.check_ban('2001:db8::1'))

    def test_rows_that_are_not_networks_are_skipped(self):
        self.add_ban('192.0.2.0', 'x')
        self.add_ban('192.0.2.1', '24')  # host bits set: read as 192.0.2.0/24
        with harness.capture_logs(logging.WARNING) as logs:
            self.assertEqual(str(asn_protection.check_ban('192.0.2.5').network), '192.0.2.0/24')
        self.assertEqual(logs.messages(), ['Skipped 1 banned prefixes that are not valid networks'])

    async def test_connect_from_a_banned_prefix_is_glined(self):
        self.add_ban('192.0.2.0', '24')
        self.assertTrue(await asn_protection.protect_banned_asn(self.bot, SENDER, '192.0.2.77'))
        self.assertTrue(self.bot.lines[1].startswith('GLINE *@192.0.2.77 7d You are connecting from a banned VPN'))


if __name__ == '__main__':
    unittest.main()

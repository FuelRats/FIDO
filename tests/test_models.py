"""
The models and every query the modules run, on a temp DB built from prod's schema
(tests/fixtures/prod_schema.sql). Synthetic data only.
"""
import contextlib
import datetime
import io
import secrets
import unittest
from unittest import mock

from config import IRC
from models import asn_blacklist, config, drones, groups, ircsessions, messagecounter, monitor, session_scope
from modules import configmanager, sessiontracker
from modules.channelprotections import droneprotection, masshighlighting, spamprotection, zalgoprotection
from modules.commands import asn_ban, channels, lockdown, mute, unmonitor, unmute
from modules.commands import monitor as monitor_command
from modules.networkprotection import asn_blacklist as asn_protection
from scripts import initializedb
from tests import harness

PROD_TABLES = {'config', 'groups', 'ircsessions', 'monitor', 'asn_blacklist', 'drones', 'messagecounter'}
JAMESON = harness.USER_NICK
HOST = harness.USER_HOST
OTHER_HOST = '192.0.2.20'
# check_ban widens a host to its /24 (IPv4) or /56 (IPv6); this /56 lies outside the banned 2001:db8::/48.
UNBANNED_HOST = '2001:db8:1::1'
ASN = 'AS64496'
ASN_NAME = 'EXAMPLE-NET'
CHANNEL = '#ratchat'
OPER_CHANNEL = '#opers'
OTHER_NICK = f'{JAMESON}2'
THIRD_NICK = f'{JAMESON}3'
BYSTANDERS = [f'{JAMESON}{n}' for n in range(2, 7)]
PHONE = '+447700900123'  # Ofcom's range reserved for drama


def now():
    return datetime.datetime.now()


class DBTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = self.enterContext(harness.TempDB())

    def add(self, *rows):
        with session_scope() as session:
            session.add_all(rows)

    def config_rows(self, module, key):
        with session_scope() as session:
            return [row.value for row in session.query(config.Config).filter_by(module=module, key=key)]

    def operator_bot(self, channel=CHANNEL) -> harness.FakeBot:
        """A FakeBot in channel, with Jameson holding op there so permission checks pass."""
        bot = harness.FakeBot()
        bot.add_user(JAMESON, channel=channel, status='o')
        return bot


class SchemaTest(DBTestCase):
    def test_loader_skips_the_reserved_table(self):
        statements = harness.schema_statements()
        self.assertEqual(len(statements), 11)
        self.assertFalse(any(statement.startswith(harness.RESERVED_STATEMENT) for statement in statements))
        self.assertTrue(PROD_TABLES <= self.db.table_names())

    def test_every_table_round_trips_through_the_orm(self):
        self.add(
            config.Config(module='channels', key='operchannel', value=OPER_CHANNEL),
            groups.Groups(group='ops', nickname=JAMESON, number=PHONE),
            ircsessions.IRCSessions(timestamp=now(), nickname=JAMESON, hostmask=HOST, network='192.0.2.0/24'),
            monitor.Monitor(timestamp=now(), nickname=JAMESON, msg=f'Reason: test ({OTHER_NICK})'),
            asn_blacklist.ASNBlacklist(timestamp=now(), asn=ASN, prefix='192.0.2.0', cidr='24',
                                       reason='test', asn_name=ASN_NAME),
            drones.Drones(timestamp=now(), nickname=JAMESON, hostmask=HOST, msg='dnsbl.example.test: proxy'),
            messagecounter.Messagecounter(timestamp=now(), nickname=JAMESON, hostmask=JAMESON, msg='Placeholder'),
        )
        for table in PROD_TABLES:
            self.assertEqual(self.db.count(table), 1, table)
        with session_scope() as session:
            row = session.query(monitor.Monitor).filter_by(nickname=JAMESON).one()
        # Rows stay readable after their scope has closed.
        self.assertEqual(row.msg, f'Reason: test ({OTHER_NICK})')
        self.assertIsInstance(row.timestamp, datetime.datetime)

    def test_scope_rolls_back_when_the_block_raises(self):
        with self.assertRaises(RuntimeError):
            with session_scope() as session:
                session.add(config.Config(module='notices', key='sms', value='on'))
                session.flush()
                raise RuntimeError('abort')
        self.assertEqual(self.db.count('config'), 0)


class SessionTrackerTest(DBTestCase):
    def test_first_connect_is_stored(self):
        self.assertEqual(sessiontracker.is_clone(JAMESON, HOST, True), (None, None))
        self.assertEqual(self.db.count('ircsessions'), 1)

    def test_same_nick_and_host_updates_the_timestamp(self):
        earlier = now() - datetime.timedelta(days=1)
        self.add(ircsessions.IRCSessions(timestamp=earlier, nickname=JAMESON, hostmask=HOST, network='192.0.2.0/24'))
        self.assertEqual(sessiontracker.is_clone(JAMESON, HOST, True), (None, None))
        with session_scope() as session:
            rows = session.query(ircsessions.IRCSessions).all()
        self.assertEqual(len(rows), 1)
        self.assertGreater(rows[0].timestamp, earlier)

    def test_other_nick_from_same_host_is_a_clone(self):
        earlier = now() - datetime.timedelta(hours=2)
        self.add(ircsessions.IRCSessions(timestamp=earlier, nickname=OTHER_NICK, hostmask=HOST, network='192.0.2.0/24'))
        clones, lasttime = sessiontracker.is_clone(JAMESON, HOST, True)
        self.assertEqual(clones, [OTHER_NICK])
        self.assertEqual(lasttime, earlier)
        self.assertEqual(self.db.count('ircsessions'), 2)

    def test_new_pair_purges_sessions_past_retention(self):
        expired = now() - datetime.timedelta(days=sessiontracker.SessionHandler.retention_time + 1)
        self.add(ircsessions.IRCSessions(timestamp=expired, nickname=THIRD_NICK, hostmask=OTHER_HOST,
                                         network='192.0.2.0/24'))
        sessiontracker.is_clone(JAMESON, HOST, True)
        with session_scope() as session:
            nicks = [row.nickname for row in session.query(ircsessions.IRCSessions)]
        self.assertEqual(nicks, [JAMESON])

    async def test_check_clone_reports_to_the_oper_channel(self):
        self.add(ircsessions.IRCSessions(timestamp=now(), nickname=OTHER_NICK, hostmask=HOST, network='192.0.2.0/24'))
        bot = harness.FakeBot()
        await sessiontracker.check_clone(bot, JAMESON, HOST)
        [(target, text)] = bot.messages()
        self.assertEqual(target, OPER_CHANNEL)
        self.assertIn(f'{JAMESON} has connected from {HOST}, previous nicknames: {OTHER_NICK}', text)


class ASNTest(DBTestCase):
    def setUp(self):
        super().setUp()
        self.add(asn_blacklist.ASNBlacklist(timestamp=now(), asn=ASN, prefix='192.0.2.0', cidr='24',
                                            reason='test', asn_name=ASN_NAME),
                 asn_blacklist.ASNBlacklist(timestamp=now(), asn=ASN, prefix='2001:db8::', cidr='48',
                                            reason='test', asn_name=ASN_NAME))

    async def test_check_ban_matches_v4_and_v6_prefixes(self):
        banned, item = await asn_protection.check_ban(None, JAMESON, '192.0.2.77')
        self.assertTrue(banned)
        self.assertEqual((item.asn, item.asn_name, item.cidr), (ASN, ASN_NAME, '24'))
        banned, item = await asn_protection.check_ban(None, JAMESON, '2001:db8:0:5::1')
        self.assertTrue(banned)
        self.assertEqual(item.cidr, '48')
        self.assertEqual(await asn_protection.check_ban(None, JAMESON, UNBANNED_HOST), (False, None))

    async def test_protect_banned_asn_reports_and_glines(self):
        bot = harness.FakeBot()
        self.assertTrue(await asn_protection.protect_banned_asn(bot, JAMESON, '192.0.2.77'))
        self.assertEqual(bot.lines[0], f'PRIVMSG {OPER_CHANNEL} :ASN BAN: User {JAMESON} connecting from '
                                       f'banned network {ASN}: {ASN_NAME} (192.0.2.0/24)')
        self.assertTrue(bot.lines[1].startswith('GLINE *@192.0.2.77 7d You are connecting from a banned VPN network'))

    async def test_asn_ban_stores_prefixes_with_a_timeout(self):
        reply = mock.Mock()
        reply.json.return_value = {
            'status': 'ok',
            'data': {'ipv4_prefixes': [{'ip': '192.0.2.128', 'cidr': 25, 'name': 'DOC-NET'}],
                     'ipv6_prefixes': [{'ip': '2001:db8:100::', 'cidr': 48, 'name': 'DOC-NET'}]},
        }
        bot = self.operator_bot()
        with mock.patch.object(asn_ban.requests, 'get', return_value=reply) as get:
            await asn_ban.ban_asn(bot, CHANNEL, JAMESON, ['AS64511', ASN])
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs['timeout'], asn_ban.HTTP_TIMEOUT)
        with session_scope() as session:
            stored = session.query(asn_blacklist.ASNBlacklist).filter_by(asn='AS64511').count()
        self.assertEqual(stored, 2)
        self.assertEqual(bot.messages(CHANNEL)[-1][1], 'ASN Ban: Blocked 1 IPv4 prefixes, 1 IPv6 prefixes.')

    async def test_asn_unban_deletes_every_prefix(self):
        bot = self.operator_bot()
        await asn_ban.unban_asn(bot, CHANNEL, JAMESON, [ASN, 'AS64511'])
        self.assertEqual(self.db.count('asn_blacklist'), 0)
        self.assertEqual([text for _, text in bot.messages(CHANNEL)],
                         [f'Unbanned ASN {ASN}.', 'AS64511 is not a banned ASN.'])


class ProtectionsTest(DBTestCase):
    async def test_mass_highlight_kicks_with_the_default_reason(self):
        bot = harness.FakeBot()
        bot.add_user(JAMESON, channel=CHANNEL)
        for nick in BYSTANDERS:
            bot.add_user(nick, hostname=OTHER_HOST, channel=CHANNEL)
        await masshighlighting.on_message(bot, CHANNEL, JAMESON, ' '.join(BYSTANDERS))
        self.assertEqual(bot.lines[0], f'KICK {CHANNEL} {JAMESON} :{configmanager.DEFAULT_KICK_REASON}')

    async def test_flood_kicks_after_the_message_limit(self):
        self.add(config.Config(module='channelprotection', key='maxmessages', value='4'),
                 config.Config(module='channelprotection', key='messageinterval', value='60'))
        bot = harness.FakeBot()
        bot.add_user(JAMESON, channel=CHANNEL)
        for _ in range(6):
            await spamprotection.on_message(bot, CHANNEL, JAMESON, 'hello')
        kicks = [line for line in bot.lines if line.startswith('KICK ')]
        self.assertEqual(kicks, [f'KICK {CHANNEL} {JAMESON} :{configmanager.DEFAULT_KICK_REASON}'])
        self.assertEqual(self.db.count('messagecounter'), 6)

    async def test_flood_skips_ops(self):
        bot = self.operator_bot()
        for _ in range(6):
            await spamprotection.on_message(bot, CHANNEL, JAMESON, 'hello')
        self.assertEqual(bot.lines, [])
        self.assertEqual(self.db.count('messagecounter'), 0)

    async def test_drone_during_lockdown_is_glined(self):
        configmanager.set_config('droneprotection', 'lockdown', 'True')
        bot = harness.FakeBot()
        report = (f'DNSBL -> {JAMESON}!jameson@{HOST} [{HOST}] appears in BL zone dnsbl.example.test '
                  f'(open proxy)')
        await droneprotection.on_message(bot, OPER_CHANNEL, OTHER_NICK, report)
        self.assertEqual(self.db.count('drones'), 1)
        self.assertIn(f'GLINE *@{HOST} 7d Connecting through a VPN or open proxy is not currently allowed.',
                      bot.lines)

    async def test_zalgo_kicks(self):
        bot = harness.FakeBot()
        bot.add_user(JAMESON, channel=CHANNEL)
        marks = '̀́̂̃̄'
        await zalgoprotection.on_message(bot, CHANNEL, JAMESON, ' '.join(c + marks for c in 'hello'))
        self.assertEqual(bot.lines[0], f'KICK {CHANNEL} {JAMESON} :{configmanager.DEFAULT_KICK_REASON}')


class CommandsTest(DBTestCase):
    async def test_join_and_part_persist_the_channel_list(self):
        bot = self.operator_bot()
        await channels.join_channel(bot, CHANNEL, JAMESON, ['#absdev'])
        self.assertIn('JOIN #absdev', bot.lines)
        self.assertEqual(self.config_rows('channels', 'join'), ['#absdev'])
        bot.add_channel('#absdev')
        await channels.part_channel(bot, CHANNEL, JAMESON, ['#absdev'])
        self.assertIn('PART #absdev', bot.lines)
        self.assertEqual(self.config_rows('channels', 'join'), [])

    async def test_monitor_and_unmonitor(self):
        bot = self.operator_bot()
        await monitor_command.invoke(bot, CHANNEL, JAMESON, [OTHER_NICK, 'repeat', 'drone'])
        self.assertIn(f'MONITOR + {OTHER_NICK}', bot.lines)
        with session_scope() as session:
            [row] = session.query(monitor.Monitor).all()
        self.assertEqual((row.nickname, row.msg), (OTHER_NICK, f'Reason: repeat drone ({JAMESON})'))
        await unmonitor.invoke(bot, CHANNEL, JAMESON, [OTHER_NICK])
        self.assertEqual(self.db.count('monitor'), 0)

    async def test_monitor_of_an_online_nick(self):
        bot = self.operator_bot()
        bot.add_user(OTHER_NICK, hostname=OTHER_HOST)['real_ip_address'] = OTHER_HOST
        await monitor_command.invoke(bot, CHANNEL, JAMESON, [OTHER_NICK])
        self.assertEqual(self.db.count('monitor'), 1)
        self.assertEqual(bot.messages(CHANNEL)[-1][1], f'I am now monitoring for {OTHER_NICK} and possible clones.')

    async def test_mute_and_unmute_read_the_mute_time(self):
        self.add(config.Config(module='channelprotection', key='mutetime', value='4'))
        bot = self.operator_bot()
        bot.add_user(OTHER_NICK, hostname=OTHER_HOST, channel=CHANNEL)
        await mute.invoke(bot, CHANNEL, JAMESON, [OTHER_NICK])
        self.assertIn(f'MODE {CHANNEL} +b ~t:4:~quiet:*!*@{OTHER_HOST}', bot.lines)
        await unmute.invoke(bot, CHANNEL, JAMESON, [OTHER_NICK])
        self.assertTrue(any(line.startswith(f'MODE {CHANNEL} -b ') for line in bot.lines))
        self.assertEqual(bot.messages(CHANNEL)[-1][1], f'Unmuted {OTHER_NICK}.')

    async def test_lockdown_sets_and_clears_its_row(self):
        bot = self.operator_bot()
        await lockdown.lockdown(bot, CHANNEL, JAMESON, [])
        self.assertEqual(self.config_rows('droneprotection', 'lockdown'), ['True'])
        self.assertIn('MODE #ratchat +b ~f:#NewRats:~G:unknown-users', bot.lines)
        await lockdown.disable_lockdown(bot, CHANNEL, JAMESON, [])
        self.assertEqual(self.config_rows('droneprotection', 'lockdown'), [])

    def test_oper_channel_falls_back_to_the_default(self):
        self.assertEqual(harness.FakeBot().get_oper_channel(), OPER_CHANNEL)
        self.add(config.Config(module='channels', key='operchannel', value='#opers-test'))
        self.assertEqual(harness.FakeBot().get_oper_channel(), '#opers-test')

    async def test_on_connect_joins_and_monitors_from_the_db(self):
        self.add(config.Config(module='channels', key='join', value=CHANNEL),
                 monitor.Monitor(timestamp=now(), nickname=OTHER_NICK, msg=f'Reason: test ({THIRD_NICK})'))
        bot = harness.FakeBot()
        password = secrets.token_urlsafe(18)
        with mock.patch.multiple(IRC, operline='fido-test', operlinePassword=password):
            await bot.on_connect()
        self.assertEqual(bot.lines, [f'OPER fido-test {password}', f'JOIN {CHANNEL}', f'MONITOR + {OTHER_NICK}'])


class InitializeDBTest(DBTestCase):
    def run_init(self, *argv) -> int:
        with harness.preserved_root_logging(), contextlib.redirect_stdout(io.StringIO()):
            return initializedb.main(list(argv))

    def seeded(self) -> dict:
        with session_scope() as session:
            return {(row.module, row.key): row.value for row in session.query(config.Config)}

    def test_empty_prod_schema_gets_every_key(self):
        self.assertEqual(self.run_init(), initializedb.EXIT_OK)
        self.assertEqual(self.seeded(), configmanager.DEFAULTS)

    def test_new_file_gets_all_tables(self):
        with harness.TempDB(schema=False) as empty:
            self.assertEqual(self.run_init(), initializedb.EXIT_OK)
            self.assertTrue(PROD_TABLES <= empty.table_names())
            self.assertEqual(empty.count('config'), len(configmanager.DEFAULTS))

    def test_existing_keys_are_kept(self):
        self.add(config.Config(module='channelprotection', key='maxmessages', value='7'))
        self.assertEqual(self.run_init(), initializedb.EXIT_OK)
        self.assertEqual(self.config_rows('channelprotection', 'maxmessages'), ['7'])
        self.assertEqual(self.db.count('config'), len(configmanager.DEFAULTS))

    def test_refuses_a_db_with_sessions(self):
        self.add(ircsessions.IRCSessions(timestamp=now(), nickname=JAMESON, hostmask=HOST, network='192.0.2.0/24'))
        self.assertEqual(self.run_init(), initializedb.EXIT_REFUSED)
        self.assertEqual(self.db.count('config'), 0)
        self.assertEqual(self.db.count('ircsessions'), 1)

    def test_refuses_a_db_with_asn_bans(self):
        self.add(asn_blacklist.ASNBlacklist(timestamp=now(), asn=ASN, prefix='192.0.2.0', cidr='24',
                                            reason='test', asn_name=ASN_NAME))
        self.assertEqual(self.run_init(), initializedb.EXIT_REFUSED)
        self.assertEqual(self.db.count('config'), 0)
        self.assertEqual(self.db.count('asn_blacklist'), 1)

    def test_seed_missing_adds_keys_and_keeps_data(self):
        self.add(ircsessions.IRCSessions(timestamp=now(), nickname=JAMESON, hostmask=HOST, network='192.0.2.0/24'),
                 asn_blacklist.ASNBlacklist(timestamp=now(), asn=ASN, prefix='192.0.2.0', cidr='24',
                                            reason='test', asn_name=ASN_NAME))
        self.assertEqual(self.run_init('--seed-missing'), initializedb.EXIT_OK)
        self.assertEqual(self.seeded(), configmanager.DEFAULTS)
        self.assertEqual((self.db.count('ircsessions'), self.db.count('asn_blacklist')), (1, 1))


if __name__ == '__main__':
    unittest.main()

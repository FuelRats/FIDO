"""
Commands on the fake bot with a temp DB from prod's schema: the exact MODE, GLINE, MONITOR, JOIN and
PRIVMSG lines, the IRC operator check for network-wide commands and the channel check for mute and
unmute. Server replies (JOIN echoes, MODE echoes, 367 ban list lines) go through pydle's parser with
FakeBot.receive. RIPEstat and SNS are mocked; nothing leaves the process. Synthetic data only.
"""
import asyncio
import datetime
import logging
import unittest
from unittest import mock

from sqlalchemy.exc import SQLAlchemyError

from tests import harness
from models import asn_blacklist, config, monitor, session_scope
from modules import access, commandhandler, configmanager, sms
from modules.commands import asn_ban, channels, fetch, monitor as monitor_command, puppet
from modules.networkprotection import asn_blacklist as asn_protection

BOT = harness.BOT_NICK
SERVER = harness.SERVER_NAME
OPER = harness.USER_NICK  # Jameson: IRC operator and channel op
OPER_HOST = harness.USER_HOST
RAT = 'Jameson2'  # channel op, not an IRC operator
CLIENT = 'Jameson3'  # no status anywhere
CLIENT_HOST = '192.0.2.20'
RATCHAT = '#ratchat'
OPERS = '#opers'
NEWRATS = '#newrats'
ASN = 'AS64496'
ASN_NAME = 'EXAMPLE-NET'
LOCKDOWN_BAN = '~forward:#NewRats:~security-group:unknown-users'


def now():
    return datetime.datetime.now()


class CommandTestCase(unittest.IsolatedAsyncioTestCase):
    """A FakeBot in #ratchat and #opers with an IRC operator, a channel op without oper status and a client."""

    def setUp(self):
        self.db = self.enterContext(harness.TempDB())
        self.bot = harness.FakeBot()
        for channel in (RATCHAT, OPERS):
            self.bot.add_user(OPER, channel=channel, status='o', oper=True)
            self.bot.add_user(RAT, hostname='192.0.2.11', channel=channel, status='o')
        self.bot.add_user(CLIENT, username='client', hostname=CLIENT_HOST, channel=RATCHAT)

    async def command(self, line, sender=OPER, channel=RATCHAT):
        """Run a channel message through the command handler, as FIDO does."""
        await commandhandler.on_channel_message(self.bot, channel, sender, line)

    async def private(self, line, sender=OPER):
        await commandhandler.on_private_message(self.bot, sender, line)

    def replies(self, target=RATCHAT):
        return [text for _, text in self.bot.messages(target)]

    def non_privmsg_lines(self):
        return [line for line in self.bot.lines if not line.startswith('PRIVMSG ')]

    def config_rows(self, module, key):
        with session_scope() as session:
            return [row.value for row in session.query(config.Config).filter_by(module=module, key=key)]

    async def server(self, line):
        await self.bot.receive(line)


class MuteTest(CommandTestCase):
    async def test_mute_one_minute(self):
        await self.command(f'!mute 1m {CLIENT}')
        self.assertEqual(self.bot.lines, [
            f'MODE {RATCHAT} -v {CLIENT}',
            f'MODE {RATCHAT} +b ~time:1:~quiet:*!*@{CLIENT_HOST}',
            f'PRIVMSG {RATCHAT} :Muted {CLIENT} for 1 minutes.',
        ])

    async def test_mute_seven_days_is_refused(self):
        await self.command(f'!mute 7d {CLIENT}')
        self.assertEqual(self.bot.lines, [
            f'PRIVMSG {RATCHAT} :Mute time must be between 1 and 9999 minutes; 10080 is not.'])

    async def test_mute_zero_minutes_is_refused(self):
        await self.command(f'!mute 0m {CLIENT}')
        self.assertEqual(self.non_privmsg_lines(), [])
        self.assertIn('between 1 and 9999 minutes', self.replies()[0])

    async def test_longest_mute_is_accepted(self):
        await self.command(f'!mute 9999m {CLIENT}')
        self.assertIn(f'MODE {RATCHAT} +b ~time:9999:~quiet:*!*@{CLIENT_HOST}', self.bot.lines)

    async def test_default_comes_from_mutetime(self):
        await self.command(f'!mute {CLIENT}')
        self.assertIn(f'MODE {RATCHAT} +b ~time:4:~quiet:*!*@{CLIENT_HOST}', self.bot.lines)
        configmanager.set_config('channelprotection', 'mutetime', '15')
        await self.command(f'!mute {CLIENT}')
        self.assertIn(f'MODE {RATCHAT} +b ~time:15:~quiet:*!*@{CLIENT_HOST}', self.bot.lines)

    async def test_mute_needs_channel_op_not_oper_status(self):
        self.bot.add_user('Jameson4', hostname='192.0.2.14', channel=RATCHAT, oper=True)
        await self.command(f'!mute 1m {CLIENT}', sender='Jameson4')
        self.assertEqual(self.bot.lines, [f'PRIVMSG {RATCHAT} :You must be a channel operator to mute.'])
        await self.command(f'!mute 1m {CLIENT}', sender=RAT)
        self.assertIn(f'MODE {RATCHAT} +b ~time:1:~quiet:*!*@{CLIENT_HOST}', self.bot.lines)


class UnmuteTest(CommandTestCase):
    async def mute_echo(self, minutes):
        """The server's echo of FIDO's +b."""
        await self.server(f':{BOT}!fido@{SERVER} MODE {RATCHAT} +b ~time:{minutes}:~quiet:*!*@{CLIENT_HOST}')

    async def test_unmute_after_mute_4(self):
        await self.command(f'!mute 4m {CLIENT}')
        await self.mute_echo(4)
        self.bot.lines.clear()
        await self.command(f'!unmute {CLIENT}')
        self.assertEqual(self.bot.lines, [f'MODE {RATCHAT} -b ~time:4:~quiet:*!*@{CLIENT_HOST}',
                                          f'PRIVMSG {RATCHAT} :Unmuted {CLIENT}.'])

    async def test_unmute_after_mute_120_from_the_ban_list(self):
        # FIDO joined after the mute was set: the entry comes from the 367 reply to MODE #ratchat b.
        await self.server(f':{SERVER} 367 {BOT} {RATCHAT} ~time:120:~quiet:*!*@{CLIENT_HOST} {RAT} 1700000000')
        await self.server(f':{SERVER} 368 {BOT} {RATCHAT} :End of Channel Ban List')
        await self.command(f'!unmute {CLIENT}', sender=RAT)
        self.assertEqual(self.bot.lines, [f'MODE {RATCHAT} -b ~time:120:~quiet:*!*@{CLIENT_HOST}',
                                          f'PRIVMSG {RATCHAT} :Unmuted {CLIENT}.'])

    async def test_unmute_with_no_mute(self):
        await self.server(f':{SERVER} 367 {BOT} {RATCHAT} *!*@{CLIENT_HOST} {RAT} 1700000000')
        await self.server(f':{SERVER} 367 {BOT} {RATCHAT} ~time:5:~quiet:*!*@192.0.2.21 {RAT} 1700000000')
        await self.command(f'!unmute {CLIENT}')
        self.assertEqual(self.bot.lines, [f'PRIVMSG {RATCHAT} :{CLIENT}: no matching mute.'])

    async def test_unmute_of_an_unknown_nick(self):
        await self.command('!unmute Jameson9')
        self.assertEqual(self.bot.lines, [f'PRIVMSG {RATCHAT} :Jameson9: no matching mute.'])

    async def test_unmute_removes_every_mute_of_the_host(self):
        await self.mute_echo(4)
        await self.server(f':{SERVER} 367 {BOT} {RATCHAT} ~TIME:30:~Quiet:*!*@{CLIENT_HOST} {RAT} 1700000000')
        await self.command(f'!unmute {CLIENT}')
        self.assertEqual(self.non_privmsg_lines(), [f'MODE {RATCHAT} -b ~time:4:~quiet:*!*@{CLIENT_HOST}',
                                                    f'MODE {RATCHAT} -b ~TIME:30:~Quiet:*!*@{CLIENT_HOST}'])

    async def test_expired_mute_leaves_the_list(self):
        await self.mute_echo(1)
        await self.server(f':{SERVER} MODE {RATCHAT} -b ~time:1:~quiet:*!*@{CLIENT_HOST}')
        await self.command(f'!unmute {CLIENT}')
        self.assertEqual(self.replies(), [f'{CLIENT}: no matching mute.'])

    async def test_unmute_needs_half_op(self):
        await self.mute_echo(4)
        await self.command(f'!unmute {CLIENT}', sender=CLIENT)
        self.assertEqual(self.bot.lines, [f'PRIVMSG {RATCHAT} :You must be a half-op or higher to unmute.'])

    async def test_own_join_requests_the_ban_list_and_367_fills_it(self):
        await self.server(f':{BOT}!fido@{SERVER} JOIN :#rescue')
        self.assertIn('MODE #rescue b', self.bot.lines)
        with harness.capture_logs(logging.DEBUG) as logs:
            for _ in range(2):
                await self.server(f':{SERVER} 367 {BOT} #rescue ~time:4:~quiet:*!*@{CLIENT_HOST} {RAT} 1700000000')
            await self.server(f':{SERVER} 368 {BOT} #rescue :End of Channel Ban List')
            await self.server(f':{SERVER} 367 {BOT} #elsewhere *!*@{CLIENT_HOST} {RAT} 1700000000')
        self.assertEqual(self.bot.channels['#rescue']['modes']['b'], [f'~time:4:~quiet:*!*@{CLIENT_HOST}'])
        self.assertFalse(any(record.levelno >= logging.WARNING for record in logs.records), logs.messages())


class LockdownTest(CommandTestCase):
    async def test_lockdown_and_unlock(self):
        await self.command('!lockdown', channel=OPERS)
        self.assertEqual(self.non_privmsg_lines(), [f'MODE {RATCHAT} +b {LOCKDOWN_BAN}'])
        self.assertEqual(self.replies(OPERS), ['LOCKDOWN: Locking down!'])
        [announcement] = self.replies(RATCHAT)
        self.assertIn('will now be G-Lined', announcement)
        self.assertNotIn('KILL', announcement)
        self.assertEqual(self.config_rows('droneprotection', 'lockdown'), ['True'])

        self.bot.lines.clear()
        await self.command('!lockdown', channel=OPERS)
        self.assertEqual(self.bot.lines, [f'PRIVMSG {OPERS} :LOCKDOWN: Lockdown is already in effect.'])

        self.bot.lines.clear()
        await self.command('!unlock', channel=OPERS)
        self.assertEqual(self.non_privmsg_lines(), [f'MODE {RATCHAT} -b {LOCKDOWN_BAN}'])
        self.assertEqual(self.config_rows('droneprotection', 'lockdown'), [])

    async def test_unlock_without_a_lockdown_row(self):
        await self.command('!unlock', channel=OPERS)
        self.assertEqual(self.bot.lines, [f"PRIVMSG {OPERS} :LOCKDOWN: Lockdown isn't enabled, doing nothing."])

    async def test_oper_versus_non_oper(self):
        await self.command('!lockdown', sender=RAT, channel=OPERS)
        self.assertEqual(self.bot.lines, [f'PRIVMSG {OPERS} :You must be an IRC operator to lock down #ratchat.'])
        self.assertEqual(self.config_rows('droneprotection', 'lockdown'), [])
        self.bot.lines.clear()
        await self.command('!lockdown', sender=OPER, channel=OPERS)
        self.assertIn(f'MODE {RATCHAT} +b {LOCKDOWN_BAN}', self.bot.lines)


class OperCheckTest(CommandTestCase):
    NETWORK_WIDE = {
        '!asn_ban AS64511 spam': 'ban networks',
        '!asn_unban AS64511': 'unban networks',
        '!asn_test 192.0.2.1': 'test banned networks',
        '!lockdown': 'lock down #ratchat',
        '!unlock': 'lift a lockdown',
        '!join #rescue': 'make FIDO join channels',
        '!part #ratchat': 'make FIDO part channels',
        '!monitor Jameson5 repeat': 'monitor nicks',
        '!watch Jameson5 repeat': 'monitor nicks',
        '!unmonitor Jameson5': 'stop monitoring nicks',
        '!smssend ops test': 'send SMS',
        f'!rcjoin {CLIENT}': '!rcjoin clients',
        '!fetch 192.0.2.1': 'fetch IP information',
        '!geoip 192.0.2.1': 'fetch IP information',
    }

    async def test_every_network_wide_command_needs_an_irc_operator(self):
        for line, action in self.NETWORK_WIDE.items():
            with self.subTest(line):
                self.bot.lines.clear()
                await self.command(line, sender=RAT, channel=OPERS)
                self.assertEqual(self.bot.lines, [f'PRIVMSG {OPERS} :You must be an IRC operator to {action}.'])

    async def test_whois_answer_is_cached_for_a_minute(self):
        with mock.patch.object(self.bot, 'whois', wraps=self.bot.whois) as whois:
            self.assertTrue(await access.is_irc_operator(self.bot, OPER))
            self.assertTrue(await access.is_irc_operator(self.bot, OPER.upper()))
            self.assertFalse(await access.is_irc_operator(self.bot, RAT))
            self.assertFalse(await access.is_irc_operator(self.bot, RAT))
            self.assertEqual(whois.await_count, 2)
            later = access.time.monotonic() + access.OPER_CACHE_SECONDS + 1
            with mock.patch.object(access, 'time', mock.Mock(monotonic=mock.Mock(return_value=later))):
                await access.is_irc_operator(self.bot, OPER)
            self.assertEqual(whois.await_count, 3)

    async def test_cache_is_cleared_on_nick_change_and_quit(self):
        self.assertTrue(await access.is_irc_operator(self.bot, OPER))
        # The oper leaves the nick; a non-oper takes it over.
        await self.server(f':{OPER}!jameson@{OPER_HOST} NICK :Jameson_away')
        self.bot.whois_replies[OPER] = dict(self.bot.whois_replies[RAT], oper=False)
        self.assertFalse(await access.is_irc_operator(self.bot, OPER))

        self.assertFalse(await access.is_irc_operator(self.bot, RAT))
        self.bot.whois_replies[RAT] = dict(self.bot.whois_replies[RAT], oper=True)
        self.assertFalse(await access.is_irc_operator(self.bot, RAT))  # cached
        await self.server(f':{RAT}!jameson2@192.0.2.11 QUIT :Quit: bye')
        self.assertTrue(await access.is_irc_operator(self.bot, RAT))

    async def assert_whois_held_across_is_not_cached(self, departure):
        """
        An operator check on OPER whose WHOIS is answered only after the server line departure
        (OPER leaving the nick) returns that answer, caches nothing, and the next check WHOISes again.
        """
        answer = self.bot.whois
        released = asyncio.Event()

        async def held(nickname):
            if nickname == OPER:
                await released.wait()
            return await answer(nickname)

        with mock.patch.object(self.bot, 'whois', side_effect=held) as whois:
            check = asyncio.create_task(access.is_irc_operator(self.bot, OPER))
            async with asyncio.timeout(harness.WAIT_TIMEOUT):
                while not whois.called:
                    await asyncio.sleep(0)
            await self.server(departure)
            released.set()
            self.assertTrue(await check)
            self.assertEqual(self.bot.oper_cache, {})
            await access.is_irc_operator(self.bot, OPER)
            self.assertEqual([call.args[0] for call in whois.call_args_list].count(OPER), 2)

    async def test_whois_held_across_a_nick_change_is_not_cached(self):
        await self.assert_whois_held_across_is_not_cached(f':{OPER}!jameson@{OPER_HOST} NICK :Jameson_away')

    async def test_whois_held_across_a_quit_is_not_cached(self):
        await self.assert_whois_held_across_is_not_cached(f':{OPER}!jameson@{OPER_HOST} QUIT :Quit: bye')

    async def test_nick_without_whois_reply_is_not_an_oper(self):
        self.assertFalse(await access.is_irc_operator(self.bot, 'Jameson9'))

    async def test_command_from_a_sender_pydle_does_not_know(self):
        await self.command(f'!mute 1m {CLIENT}', sender='Jameson9')
        self.assertEqual(self.bot.lines, [f'PRIVMSG {RATCHAT} :You must be a channel operator to mute.'])

    async def test_bot_hosts_are_ignored(self):
        configmanager.set_config('commandhandler', 'bothost', '192.0.2.11')
        await self.command(f'!mute 1m {CLIENT}', sender=RAT)
        self.assertEqual(self.bot.lines, [])


class WhoisFromServerTest(CommandTestCase):
    """
    The IRC operator check on WHOIS replies that pydle parses, worded as UnrealIRCd 6.2.6 sends them.
    A services bot (BotServ, umodes +BioqS) gets the operator 313, but also the network service 313
    and the bot line 335.
    """
    BOT_HOST = 'services.example.test'
    OPERATOR_313 = 'is an IRC Operator (jameson) [netadmin]'
    SERVICE_313 = 'is a Network Service'
    BOT_335 = 'is a \x02Bot\x02 on Example'

    def setUp(self):
        super().setUp()
        self.bot.whois_from_server = True

    def whois_reply(self, nick, *extra):
        """311, 312, the extra (numeric, text) lines, then 318."""
        lines = [f':{SERVER} 311 {BOT} {nick} {nick.lower()} {self.BOT_HOST} * :{nick}',
                 f':{SERVER} 312 {BOT} {nick} {SERVER} :Example server']
        lines += [f':{SERVER} {numeric} {BOT} {nick} :{text}' for numeric, text in extra]
        return lines + [f':{SERVER} 318 {BOT} {nick} :End of /WHOIS list.']

    async def lockdown_by(self, nick, reply):
        task = asyncio.create_task(self.command('!lockdown', sender=nick, channel=OPERS))
        await self.bot.whois_pending(nick)
        for line in reply:
            await self.server(line)
        await task

    async def test_services_bot_is_not_an_irc_operator(self):
        replies = {
            'operator, network service and bot lines': (('313', self.OPERATOR_313), ('313', self.SERVICE_313),
                                                        ('335', self.BOT_335)),
            'operator and network service lines': (('313', self.OPERATOR_313), ('313', self.SERVICE_313)),
            'operator and bot lines': (('313', self.OPERATOR_313), ('335', self.BOT_335)),
        }
        for name, extra in replies.items():
            with self.subTest(name):
                self.bot.lines.clear()
                self.bot.oper_cache.clear()
                await self.lockdown_by(RAT, self.whois_reply(RAT, *extra))
                self.assertEqual(self.non_privmsg_lines(), [f'WHOIS {RAT}'])
                self.assertEqual(self.replies(OPERS), ['You must be an IRC operator to lock down #ratchat.'])
                self.assertEqual(self.config_rows('droneprotection', 'lockdown'), [])

    async def test_irc_operator_passes(self):
        await self.lockdown_by(OPER, self.whois_reply(OPER, ('313', self.OPERATOR_313)))
        self.assertEqual(self.non_privmsg_lines(), [f'WHOIS {OPER}', f'MODE {RATCHAT} +b {LOCKDOWN_BAN}'])
        self.assertEqual(self.config_rows('droneprotection', 'lockdown'), ['True'])


class PuppetTest(CommandTestCase):
    async def test_say_and_act_need_an_irc_operator(self):
        await self.private('!say #ratchat hello', sender=RAT)
        self.assertEqual(self.bot.lines, [f'PRIVMSG {RAT} :You must be an IRC operator to use !say.'])
        self.bot.lines.clear()
        await self.private('!say #ratchat hello there')
        await self.private('!act #ratchat waves')
        self.assertEqual(self.bot.lines, [f'PRIVMSG {RATCHAT} :hello there', f'PRIVMSG {RATCHAT} :\x01ACTION waves\x01'])

    async def test_line_breaks_in_a_puppet_message_are_not_sent_raw(self):
        # IRC input cannot carry CR or LF; this checks the send path if one ever got through.
        await puppet.say(self.bot, OPER, ['#ratchat', 'hello\r\nQUIT :gone\r\nKICK #ratchat Jameson3'])
        await puppet.act(self.bot, OPER, ['#ratchat', 'waves\r\nQUIT'])
        self.assertTrue(all(line.startswith(f'PRIVMSG {RATCHAT} ') for line in self.bot.lines), self.bot.lines)
        self.assertEqual([text for _, text in self.bot.messages(RATCHAT)][:3],
                         ['hello', 'QUIT :gone', 'KICK #ratchat Jameson3'])
        self.assertEqual(len(self.bot.lines), 4)  # the ACTION's line break is CTCP-quoted, not a new line

    async def test_unknown_channel(self):
        await self.private('!say #rescue hello')
        self.assertEqual(self.bot.lines, [f'PRIVMSG {OPER} :Invalid channel'])


class MonitorTest(CommandTestCase):
    def monitor_rows(self):
        with session_scope() as session:
            return [(row.nickname, row.msg) for row in session.query(monitor.Monitor).order_by(monitor.Monitor.id)]

    async def test_monitor_with_and_without_a_reason(self):
        await self.command('!monitor Jameson5 ban evasion')
        await self.command('!monitor Jameson6')
        self.assertEqual(self.monitor_rows(), [('Jameson5', f'Reason: ban evasion ({OPER})'),
                                               ('Jameson6', f'No reason given ({OPER})')])
        self.assertEqual(self.non_privmsg_lines(), ['MONITOR + Jameson5', 'MONITOR + Jameson6'])
        self.assertEqual(self.replies()[0], "Nickname not found online, but I'll keep an eye out for that exact name.")

    async def test_monitor_of_an_online_nick(self):
        await self.command(f'!monitor {CLIENT} repeat')
        self.assertEqual(self.replies(), [f'I am now monitoring for {CLIENT} and possible clones.'])

    async def test_duplicate_is_rejected(self):
        await self.command('!monitor Jameson5 one')
        self.bot.lines.clear()
        await self.command('!monitor Jameson5 two')
        self.assertEqual(self.bot.lines, [f'PRIVMSG {RATCHAT} :I am already monitoring for Jameson5.'])
        self.assertEqual(len(self.monitor_rows()), 1)

    async def test_database_error_sends_no_monitor_and_no_success_reply(self):
        with mock.patch.object(monitor_command, 'session_scope', side_effect=SQLAlchemyError('locked')), \
                harness.capture_logs(logging.ERROR):
            await self.command('!monitor Jameson5')
        self.assertEqual(self.bot.lines, [f'PRIVMSG {RATCHAT} :Database error while adding monitor nick.'])

    async def test_unmonitor_of_a_duplicate(self):
        with session_scope() as session:
            for reason in ('one', 'two'):
                session.add(monitor.Monitor(timestamp=now(), nickname='Jameson5', msg=f'Reason: {reason} ({OPER})'))
        await self.bot.monitor('Jameson5')  # as on_connect does for every stored row
        self.bot.lines.clear()
        await self.command('!unmonitor Jameson5')
        self.assertEqual(self.bot.lines, ['MONITOR - Jameson5', f'PRIVMSG {RATCHAT} :Stopped monitoring for Jameson5.'])
        self.assertEqual(self.monitor_rows(), [])
        self.assertFalse(self.bot.is_monitoring('Jameson5'))

    async def test_unmonitor_of_an_unmonitored_nick(self):
        await self.command('!unmonitor Jameson5')
        self.assertEqual(self.bot.lines, [f'PRIVMSG {RATCHAT} :I am not monitoring for Jameson5.'])


class ASNTestCase(CommandTestCase):
    def setUp(self):
        super().setUp()
        with session_scope() as session:
            session.add(asn_blacklist.ASNBlacklist(timestamp=now(), asn=ASN, prefix='192.0.2.0', cidr='24',
                                                   reason='test', asn_name=ASN_NAME))

    def stored(self, asn):
        with session_scope() as session:
            return [(row.prefix, row.cidr, row.reason, row.asn_name, row.timestamp is not None)
                    for row in session.query(asn_blacklist.ASNBlacklist).filter_by(asn=asn).order_by(
                        asn_blacklist.ASNBlacklist.id)]


def ripestat(prefixes_body, overview_body=None):
    """A requests.get stand-in answering the two RIPEstat URLs."""
    bodies = {asn_ban.ANNOUNCED_PREFIXES_URL: prefixes_body,
              asn_ban.AS_OVERVIEW_URL: overview_body or {'status': 'ok', 'data': {'holder': 'DOC-NET Example'}}}

    def get(url, **_kwargs):
        response = mock.Mock()
        response.json.return_value = bodies[url]
        return response
    return mock.Mock(side_effect=get)


class ASNBanTest(ASNTestCase):
    PREFIXES = {'status': 'ok', 'data': {'resource': '64511', 'prefixes': [
        {'prefix': '192.0.2.128/25', 'timelines': []}, {'prefix': '2001:db8:100::/48', 'timelines': []}]}}

    async def test_asn_ban_with_ripestat_mocked(self):
        get = ripestat(self.PREFIXES)
        with mock.patch.object(asn_ban.requests, 'get', get):
            await self.command('!asn_ban AS64511 VPN abuse, ticket 7', channel=OPERS)
        self.assertEqual(get.call_args_list, [
            mock.call(asn_ban.ANNOUNCED_PREFIXES_URL, params={'resource': 'AS64511', 'sourceapp': 'fuelrats-fido'},
                      timeout=10),
            mock.call(asn_ban.AS_OVERVIEW_URL, params={'resource': 'AS64511'}, timeout=10),
        ])
        self.assertEqual(self.stored('AS64511'), [
            ('192.0.2.128', '25', 'VPN abuse, ticket 7', 'DOC-NET Example', True),
            ('2001:db8:100::', '48', 'VPN abuse, ticket 7', 'DOC-NET Example', True),
        ])
        self.assertEqual(self.bot.lines,
                         [f'PRIVMSG {OPERS} :ASN Ban: Blocked 2 prefixes of AS64511 (DOC-NET Example): 1 IPv4, 1 IPv6.'])

    async def test_new_prefixes_apply_to_the_next_connect(self):
        self.assertIsNone(asn_protection.check_ban('2001:db8:100::1'))
        with mock.patch.object(asn_ban.requests, 'get', ripestat(self.PREFIXES)):
            await self.command('!asn_ban AS64511', channel=OPERS)
        self.assertEqual(str(asn_protection.check_ban('2001:db8:100::1').network), '2001:db8:100::/48')
        self.assertEqual(self.stored('AS64511')[0][2], None)  # no reason given

    async def test_failed_status_stores_nothing(self):
        failed = {'status': 'error', 'messages': [['error', 'unknown resource']]}
        with mock.patch.object(asn_ban.requests, 'get', ripestat(failed)), harness.capture_logs(logging.ERROR):
            await self.command('!asn_ban AS64511', channel=OPERS)
        self.assertEqual(self.stored('AS64511'), [])
        self.assertEqual(self.replies(OPERS), ["ASN Ban: could not fetch the prefixes of AS64511 from RIPEstat "
                                               "(status 'error'); nothing banned."])

    async def test_request_error_stores_nothing(self):
        error = asn_ban.requests.ConnectionError('refused')
        with mock.patch.object(asn_ban.requests, 'get', side_effect=error), harness.capture_logs(logging.ERROR):
            await self.command('!asn_ban AS64511', channel=OPERS)
        self.assertEqual(self.stored('AS64511'), [])
        self.assertIn('ConnectionError', self.replies(OPERS)[0])

    async def test_missing_holder_name_still_bans(self):
        failed = {'status': 'error'}
        with mock.patch.object(asn_ban.requests, 'get', ripestat(self.PREFIXES, failed)), \
                harness.capture_logs(logging.ERROR):
            await self.command('!asn_ban AS64511', channel=OPERS)
        self.assertEqual([row[3] for row in self.stored('AS64511')], [None, None])
        self.assertIn('(unknown name)', self.replies(OPERS)[0])

    async def test_already_banned_and_usage(self):
        get = ripestat(self.PREFIXES)
        with mock.patch.object(asn_ban.requests, 'get', get):
            await self.command(f'!asn_ban {ASN}', channel=OPERS)
            await self.command('!asn_ban spam', channel=OPERS)
        get.assert_not_called()
        self.assertEqual(self.replies(OPERS), [f'ASN Ban: {ASN} is already banned.',
                                               'Usage: !asn_ban AS<number> [AS<number> ...] [reason]'])

    async def test_asn_unban_reloads_the_prefixes(self):
        self.assertIsNotNone(asn_protection.check_ban('192.0.2.77'))
        await self.command(f'!asn_unban {ASN}', channel=OPERS)
        self.assertIsNone(asn_protection.check_ban('192.0.2.77'))
        self.assertEqual(self.replies(OPERS), [f'Unbanned ASN {ASN}.'])


class ASNTestCommandTest(ASNTestCase):
    async def test_banned_address_is_reported_without_a_gline(self):
        await self.command('!asn_test 192.0.2.77', channel=OPERS)
        self.assertEqual(self.bot.lines, [f'PRIVMSG {OPERS} :ASN test: 192.0.2.77 would be banned by 192.0.2.0/24 '
                                          f'({ASN}: {ASN_NAME}).'])

    async def test_address_outside_the_bans(self):
        await self.command('!asn_test 2001:db8:1::1', channel=OPERS)
        self.assertEqual(self.bot.lines, [f'PRIVMSG {OPERS} :ASN test: 2001:db8:1::1 is not banned.'])

    async def test_invalid_address(self):
        await self.command('!asn_test example.test', channel=OPERS)
        self.assertEqual(self.bot.lines, [f'PRIVMSG {OPERS} :example.test is not an IP address.'])


class JoinPartTest(CommandTestCase):
    async def test_join_with_the_echo_is_remembered(self):
        self.bot.echo_joins = True
        await self.command('!join #rescue #Rescue')
        self.assertEqual(self.bot.lines[0], 'JOIN #rescue')
        self.assertEqual(self.bot.lines.count('JOIN #rescue') + self.bot.lines.count('JOIN #Rescue'), 1)
        self.assertEqual(self.config_rows('channels', 'join'), ['#rescue'])
        self.assertEqual(self.replies(), ['Joined: #rescue.'])

    async def test_comma_separated_channels_are_joined_and_remembered_one_by_one(self):
        self.bot.echo_joins = True
        with mock.patch.object(channels, 'JOIN_CONFIRM_TIMEOUT', 0.5):
            await self.command('!join #rescue,#drillrats,#Rescue')
        self.assertEqual([line for line in self.bot.lines if line.startswith('JOIN ')],
                         ['JOIN #rescue', 'JOIN #drillrats'])
        self.assertEqual(self.config_rows('channels', 'join'), ['#rescue', '#drillrats'])
        self.assertEqual(self.replies(), ['Joined: #rescue, #drillrats.'])

    async def test_join_without_an_echo(self):
        with mock.patch.object(channels, 'JOIN_CONFIRM_TIMEOUT', 0.05):
            await self.command('!join #rescue')
        self.assertEqual(self.non_privmsg_lines(), ['JOIN #rescue'])
        self.assertEqual(self.config_rows('channels', 'join'), [])
        self.assertEqual(self.replies(), ['Could not join within 0.05 s, not remembered: #rescue.'])
        self.assertEqual(self.bot._join_waiters, {})

    async def test_late_echo_is_not_remembered(self):
        with mock.patch.object(channels, 'JOIN_CONFIRM_TIMEOUT', 0.05):
            await self.command('!join #rescue')
        await self.server(f':{BOT}!fido@{SERVER} JOIN :#rescue')
        self.assertEqual(self.config_rows('channels', 'join'), [])

    async def test_echo_while_waiting(self):
        task = asyncio.create_task(self.command('!join #rescue'))
        while 'JOIN #rescue' not in self.bot.lines:
            await asyncio.sleep(0)
        await self.server(f':{BOT}!fido@{SERVER} JOIN :#rescue')
        await task
        self.assertEqual(self.config_rows('channels', 'join'), ['#rescue'])

    async def test_part(self):
        configmanager.set_config('channels', 'join', OPERS)
        await self.command(f'!part {OPERS}')
        self.assertEqual(self.non_privmsg_lines(), [f'PART {OPERS}'])
        self.assertEqual(self.config_rows('channels', 'join'), [])


class SMSCommandTest(CommandTestCase):
    def setUp(self):
        super().setUp()
        self.send = self.enterContext(mock.patch.object(sms, 'send_to_group', mock.AsyncMock(return_value=True)))

    async def test_smssend_publishes_to_the_group(self):
        await self.command('!smssend ops Need ops in #ratchat, thanks', channel=OPERS)
        self.send.assert_awaited_once_with('ops', 'Need ops in #ratchat, thanks')
        self.assertEqual(self.replies(OPERS), ['SMS sent to group ops.'])

    async def test_failed_publish_is_reported(self):
        self.send.return_value = False
        await self.command('!smssend ops test', channel=OPERS)
        self.assertEqual(self.replies(OPERS), ['SMS to group ops was not sent; see the log.'])

    async def test_usage_and_non_oper(self):
        await self.command('!smssend ops', channel=OPERS)
        await self.command('!smssend ops test', sender=RAT, channel=OPERS)
        self.send.assert_not_awaited()
        self.assertEqual(self.replies(OPERS), ['Usage: !smssend <group> <text>',
                                               'You must be an IRC operator to send SMS.'])

    async def test_nexmo_commands_are_gone(self):
        for command in ('nexmosend', 'nexmoadd', 'stonks'):
            self.assertNotIn(command, commandhandler.commandsDict)


class FetchTest(CommandTestCase):
    async def test_missing_whois_host_line_is_reported(self):
        with mock.patch.object(fetch.requests, 'get') as get:
            await self.command(f'!fetch {CLIENT}', channel=OPERS)
        get.assert_not_called()
        self.assertEqual(self.replies(OPERS),
                         [f'No IP address for {CLIENT}: the WHOIS reply had no host line (378).'])

    async def test_real_ip_from_whois(self):
        self.bot.add_user(CLIENT, username='client', hostname='client.example.test', channel=RATCHAT,
                          real_ip=CLIENT_HOST)
        reply = mock.Mock()
        reply.json.return_value = {'ip': CLIENT_HOST, 'country': 'NO', 'org': 'AS64496 Example'}
        with mock.patch.object(fetch.requests, 'get', return_value=reply) as get:
            await self.command(f'!fetch {CLIENT}', channel=OPERS)
        self.assertEqual(get.call_args.args, (f'https://ipinfo.io/{CLIENT_HOST}',))
        self.assertIn(f'IP Information {CLIENT_HOST}:', self.replies(OPERS)[0])

    async def test_a_failed_lookup_is_reported_and_the_next_address_still_answered(self):
        good = mock.Mock()
        good.json.return_value = {'ip': '192.0.2.1', 'country': 'NO', 'org': 'AS64496 Example'}
        not_json = mock.Mock()
        not_json.json.side_effect = fetch.requests.exceptions.JSONDecodeError('Expecting value', '<html>', 0)
        get = mock.Mock(side_effect=[good, fetch.requests.exceptions.ReadTimeout('read timed out'), not_json, good])
        with mock.patch.object(fetch.requests, 'get', get), harness.capture_logs(logging.WARNING):
            await self.command('!fetch 192.0.2.1 192.0.2.2 192.0.2.3 192.0.2.4', channel=OPERS)
        replies = self.replies(OPERS)
        self.assertEqual(len(replies), 4, replies)
        self.assertTrue(replies[0].startswith('IP Information 192.0.2.1:'), replies)
        self.assertEqual(replies[1:3], ['Could not fetch IP information for 192.0.2.2: ReadTimeout',
                                        'Could not fetch IP information for 192.0.2.3: JSONDecodeError'])
        self.assertTrue(replies[3].startswith('IP Information 192.0.2.1:'), replies)
        self.assertEqual([call.kwargs.get('timeout') for call in get.call_args_list], [fetch.HTTP_TIMEOUT] * 4)

    async def test_operations_channel_is_not_allowed(self):
        self.bot.add_user(OPER, channel='#operations', status='o', oper=True)
        await self.command('!fetch 192.0.2.1', channel='#operations')
        self.assertEqual(self.replies('#operations'), ['This command can only be used in certain channels.'])


class RcjoinTest(CommandTestCase):
    async def test_rcjoin_by_an_oper(self):
        await self.command(f'!rcjoin {CLIENT}', channel=OPERS)
        self.assertEqual(self.bot.lines, [f'PRIVMSG {OPERS} :{CLIENT} is being joined to #ratchat.',
                                          f'SAJOIN {CLIENT} #ratchat'])


if __name__ == '__main__':
    unittest.main()

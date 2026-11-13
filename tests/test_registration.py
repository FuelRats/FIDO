"""
FIDO's registration, run as real FIDO sessions against tests/fake_ircd.py. pydle completes
registration at 001 with a synthetic NICK whose handling waits for a WHOIS (WHOX is not known
before 005) and then for a second WHOIS of FIDO's nick. The tests hold those answers back, by
their order on the connection, to check the channels FIDO joins at the end of the MOTD, a channel
the server joins it to after OPER, the nick check at 001 and a shutdown during the second WHOIS.
Also: the numerics UnrealIRCd 6 sends that pydle has no handler for, lines handled after the
disconnect, and the test harness's check for handlers that raise. Synthetic data only.
"""
import asyncio
import base64
import contextlib
import logging
import secrets
import unittest
from unittest import mock

import fido
from models import config, session_scope
from tests import harness
from tests.fake_ircd import CLIENT, SERVER, SERVER_NAME
from tests.test_runtime import SHUTDOWN_WITHIN, SessionTestCase

BOT = harness.BOT_NICK
MEMBER = harness.USER_NICK
CHANNELS = ['#opers', '#ratchat']
OPER_CHANNEL = '#opers'
BAN = '~time:30:~quiet:*!*@192.0.2.66'
LATE = 0.3  # seconds the answer to pydle's WHOIS at 001 is held after the MOTD ended


class RegistrationTestCase(SessionTestCase):
    def remember_channels(self, channels):
        """Rows for the channels FIDO joins at connect, as !join writes them."""
        with session_scope() as session:
            for channel in channels:
                session.add(config.Config(module='channels', key='join', value=channel))

    async def start_ircd(self, **kwargs):
        ircd = await super().start_ircd(**kwargs)
        ircd.channel_users = ['@' + MEMBER]
        ircd.channel_bans = [BAN]
        return ircd

    async def eventually(self, predicate) -> bool:
        """Whether predicate becomes true within the usual wait."""
        try:
            await self.wait_until(predicate)
        except TimeoutError:
            return False
        return True

    def server_sent(self, ircd, code: str) -> bool:
        return any(who == SERVER and self.numeric(code)(line) for who, line in ircd.transcript)

    def tracebacks(self) -> list:
        return [message for message in self.logs.rendered() if 'Traceback' in message]

    def assert_tracked(self, ircd, client, channels):
        """Each channel is in client.channels with FIDO and Jameson, Jameson's op, +nt and the ban."""
        listed = all(f'MODE {channel} b' in ircd.received for channel in channels)
        self.assertTrue(listed, f"FIDO did not list the bans of {channels}; its JOIN and MODE lines: "
                                f"{[line for line in ircd.received if line.startswith(('JOIN ', 'MODE '))]!r}")
        for channel in channels:
            with self.subTest(channel=channel):
                self.assertIn(channel, client.channels)
                self.assertEqual(client.channels[channel]['users'], {BOT, MEMBER})
                modes = client.channels[channel]['modes']
                self.assertEqual(modes.get('o'), [MEMBER])
                self.assertTrue(modes.get('n'))
                self.assertTrue(modes.get('t'))
                self.assertEqual(modes.get('b'), [BAN])

    async def held_session(self, joined, **ircd_settings):
        """A session whose server holds every WHOIS answer; it returns once the MOTD ended and LATE passed."""
        self.remember_channels(joined)
        ircd = await self.start_ircd()
        ircd.hold_whois_from = 1
        for name, value in ircd_settings.items():
            setattr(ircd, name, value)
        self.configure(ircd.port)
        client, task = await self.start_session()
        await ircd.wait_for_line('WHOIS ')
        await self.wait_until(lambda: self.server_sent(ircd, '376'))
        await asyncio.sleep(LATE)
        return ircd, client, task

    async def settle_after_release(self, ircd, channels):
        """Release the held answers, then wait for the bans of channels and pydle's two WHOIS at 001."""
        await ircd.release_whois()
        await self.eventually(lambda: all(f'MODE {channel} b' in ircd.received for channel in channels))
        await self.eventually(lambda: len(self.sent(ircd, 'WHOIS ')) >= 2)
        await self.sync(ircd, 'settled-1')
        await self.sync(ircd, 'settled-2')


class ConnectChannelsTest(RegistrationTestCase):
    async def test_channels_joined_at_connect_are_tracked_when_the_whois_at_001_is_answered_late(self):
        ircd, client, task = await self.held_session(CHANNELS)
        await self.settle_after_release(ircd, CHANNELS)

        # The scenario: 001 came before 005, and the MOTD ended before pydle's WHOIS was answered.
        self.assertLess(self.index(ircd, SERVER, self.numeric('001')), self.index(ircd, SERVER, self.numeric('005')))
        self.assertLess(self.index(ircd, SERVER, self.numeric('376')), self.index(ircd, SERVER, self.numeric('318')))
        self.assertEqual(sorted(self.sent(ircd, 'JOIN ')), sorted(f'JOIN {channel}' for channel in CHANNELS))
        self.assert_tracked(ircd, client, CHANNELS)
        # pydle's synthetic NICK at 001 went from FIDO's nick to itself: FIDO's user entry is back
        # (from the second WHOIS), and the session goes on.
        self.assertEqual(client.nickname, BOT)
        self.assertEqual(client.users[BOT]['hostname'], SERVER_NAME)
        self.assertFalse(task.done())

        # A channel command from an op reaches its handler; !unmute without a nick answers with its usage.
        await ircd.send(f":{MEMBER}!jameson@{harness.USER_HOST} PRIVMSG {CHANNELS[0]} :!unmute")
        await self.sync(ircd, 'command')
        self.assertIn(f'PRIVMSG {CHANNELS[0]} :Usage: !unmute <nickname>', ircd.received)
        self.assertEqual(self.tracebacks(), [])
        self.assertFalse(self.logged('Failed to execute'))
        client.request_shutdown()
        self.assertEqual((await self.exit_code(task))[0], fido.EXIT_OK)

    async def test_channel_the_server_joins_after_oper_is_tracked(self):
        ircd, client, task = await self.held_session(['#ratchat'], oper_auto_join=[OPER_CHANNEL])
        await self.settle_after_release(ircd, [OPER_CHANNEL, '#ratchat'])

        # The scenario: the server's JOIN came after 381 and before the answer to pydle's WHOIS.
        echo = self.index(ircd, SERVER, lambda line: line.endswith(f' JOIN :{OPER_CHANNEL}'))
        self.assertLess(self.index(ircd, SERVER, self.numeric('381')), echo)
        self.assertLess(echo, self.index(ircd, SERVER, self.numeric('318')))
        self.assertNotIn(f'JOIN {OPER_CHANNEL}', ircd.received)
        self.assert_tracked(ircd, client, [OPER_CHANNEL, '#ratchat'])
        self.assertEqual(self.tracebacks(), [])
        client.request_shutdown()
        self.assertEqual((await self.exit_code(task))[0], fido.EXIT_OK)

    async def test_whois_at_001_never_answered_still_opers_and_tracks_the_channels(self):
        ircd, client, task = await self.held_session(CHANNELS)
        await self.eventually(lambda: all(f'MODE {channel} b' in ircd.received for channel in CHANNELS))
        await self.sync(ircd, 'tracked')
        self.assertTrue(client.opered)
        self.assert_tracked(ircd, client, CHANNELS)
        self.assertFalse(task.done())


class NickCheckTest(RegistrationTestCase):
    async def test_shutdown_during_the_whois_at_001_exits_0(self):
        ircd = await self.start_ircd()
        ircd.hold_whois_from = 2  # pydle's second WHOIS at 001, answered just before QUIT's ERROR
        self.configure(ircd.port)
        client, task = await self.start_session()
        await self.wait_until(lambda: client.opered)
        await self.wait_until(lambda: len(self.sent(ircd, 'WHOIS ')) >= 2)
        client.request_shutdown()
        code, elapsed = await self.exit_code(task)

        # The scenario: the held 318 went out after the QUIT, in the same write as the ERROR.
        error = self.index(ircd, SERVER, lambda line: line.startswith('ERROR '))
        self.assertTrue(self.numeric('318')(ircd.transcript[error - 1][1]), ircd.transcript[error - 1])
        self.assertLess(self.index(ircd, CLIENT, lambda line: line.startswith('QUIT ')), error - 1)
        self.assertEqual(code, fido.EXIT_OK)
        self.assertLess(elapsed, SHUTDOWN_WITHIN)
        self.assertFalse(self.logged('registered as'))
        self.assertEqual(self.tracebacks(), [])

    async def test_registered_under_another_nick_exits_1_before_the_whois_at_001_is_answered(self):
        ircd = await self.start_ircd()
        ircd.taken_nicks.add(BOT)
        ircd.hold_whois_from = 1
        self.configure(ircd.port)
        _, task = await self.start_session()
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertTrue(self.logged(f'registered as {BOT}_, not {BOT}'))


class UnhandledNumericsTest(unittest.IsolatedAsyncioTestCase):
    """UnrealIRCd 6 numerics pydle 1.2.0 has no handler for are dropped without a WARNING."""

    LINES = [
        f":{SERVER_NAME} 396 {BOT} Clk-3A1B2C3D.example.test :is now your displayed host",
        f":{SERVER_NAME} 276 {BOT} {MEMBER} :has client certificate fingerprint 0123456789abcdef",
        f":{SERVER_NAME} 320 {BOT} {MEMBER} :is a Rat",
        f":{SERVER_NAME} 335 {BOT} {BOT} :is a \x02Bot\x02 on Example",
        f":{SERVER_NAME} 344 {BOT} {MEMBER} XX :is connecting from Example Country",
        f":{SERVER_NAME} 379 {BOT} {MEMBER} :is using modes +iwx",
        f":{SERVER_NAME} 569 {BOT} {MEMBER} 64496 :is connecting from AS64496 [Example Network]",
    ]

    async def test_whois_and_displayed_host_numerics_log_no_warning(self):
        bot = harness.FakeBot()
        with harness.capture_logs(logging.DEBUG) as logs:
            for line in self.LINES:
                await bot.receive(line)
            warnings_before_control = [record.getMessage() for record in logs.records
                                       if record.levelno >= logging.WARNING]
            # Positive control: a numeric no one handles still warns.
            await bot.receive(f":{SERVER_NAME} 998 {BOT} :unassigned")
        self.assertEqual(warnings_before_control, [])
        self.assertTrue(any(record.levelno == logging.WARNING and 'Unknown command' in record.getMessage()
                            for record in logs.records))
        self.assertEqual(bot.lines, [])


class LinesAfterTheDisconnectTest(unittest.IsolatedAsyncioTestCase):
    """
    pydle handles each received line in a task of its own, which can run after the session's
    teardown disconnected and pydle reset its state, registered included. pydle 1.2.0 handles 002,
    003 and the 25x/26x numerics like 001, as the end of registration.
    """

    LATE_LINES = [
        f":{SERVER_NAME} 002 {BOT} :Your host is {SERVER_NAME}, running version fakeircd-1",
        f":{SERVER_NAME} 003 {BOT} :This server was created today",
        f":{SERVER_NAME} 251 {BOT} :There are 2 users and 0 invisible on 1 servers",
        f":{SERVER_NAME} 266 {BOT} 2 2 :Current global users 2, max 2",
    ]
    ERROR_LINE = f"ERROR :Closing Link: {BOT}[192.0.2.1] (Killed ({MEMBER} (testing)))"
    NOT_SENT = 'Not sent after the disconnect:'  # FIDO's DEBUG line for a dropped write

    async def disconnected_bot(self):
        bot = harness.FakeBot()
        bot.whois_from_server = True  # pydle's own WHOIS, written to the connection
        await bot.disconnect(expected=True)
        self.assertFalse(bot.connected)
        self.assertFalse(bot.registered)
        return bot

    @staticmethod
    def logged_in(logs, text: str) -> bool:
        """Whether a captured record, exception text included, contains text."""
        return any(text in message for message in logs.rendered())

    async def test_registration_lines_after_the_disconnect_send_nothing(self):
        bot = await self.disconnected_bot()
        with harness.capture_logs(logging.DEBUG) as logs:
            for line in self.LATE_LINES:
                with self.subTest(line.split()[1]):
                    async with asyncio.timeout(harness.WAIT_TIMEOUT):
                        await bot.receive(line)
                    self.assertEqual(bot.lines, [])
                    self.assertFalse(bot.registered)
        self.assertFalse(any(harness.PYDLE_HANDLER_FAILURE in message for message in logs.messages()))

    async def test_error_after_the_disconnect_still_logs_the_servers_reason(self):
        bot = await self.disconnected_bot()
        with harness.capture_logs(logging.DEBUG) as logs:
            await bot.receive(self.ERROR_LINE)
        self.assertTrue(any('Closing Link' in message for message in logs.rendered()), logs.messages())
        self.assertEqual(bot.lines, [])

    async def test_a_handler_that_resumes_after_the_disconnect_sends_nothing(self):
        # A shutdown during the WHOIS at 001: 001's handler waits on pydle's WHOIS of FIDO's nick
        # (no WHOX before 005). Its answer and QUIT's ERROR are handled first, so the handler
        # resumes after the disconnect, and pydle's AccountSupport WHOISes the nick once more.
        bot = harness.FakeBot()
        bot.whois_from_server = True
        bot.registered = False
        del bot._isupport['WHOX']
        bot.shutdown_requested = True
        with harness.capture_logs(logging.DEBUG) as logs:
            registration = asyncio.create_task(bot.receive(f":{SERVER_NAME} 001 {BOT} :Welcome to Example"))
            await bot.whois_pending(BOT)
            sent = list(bot.lines)
            await bot.receive(f":{SERVER_NAME} 318 {BOT} {BOT} :End of /WHOIS list.")
            await bot.receive(f"ERROR :Closing Link: {BOT}[192.0.2.1] (Quit: {fido.QUIT_MESSAGE})")
            self.assertFalse(bot.connected)
            async with asyncio.timeout(harness.WAIT_TIMEOUT):
                while not registration.done() and not self.logged_in(logs, f'{self.NOT_SENT} WHOIS'):
                    await asyncio.sleep(0)
            if registration.done():
                self.fail(f"001's handler failed after the disconnect: {registration.exception()}")
            # pydle's WHOIS now waits for an answer that never comes; asyncio.run cancels it at exit.
            registration.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await registration
        self.assertEqual(sent, [f'WHOIS {BOT}'])
        self.assertEqual(bot.lines, sent)
        self.assertFalse(self.logged_in(logs, harness.PYDLE_HANDLER_FAILURE))
        self.assertFalse(self.logged_in(logs, 'Traceback'))

    async def test_credential_writes_after_the_disconnect_are_dropped_without_their_text(self):
        # OPER and the SASL response skip pydle's _send and its DEBUG log; they reach the
        # connection directly.
        oper_password = secrets.token_urlsafe(12)
        sasl_password = secrets.token_urlsafe(12)
        bot = await self.disconnected_bot()
        with mock.patch.multiple(fido.IRC, operline='fido-test', operlinePassword=oper_password,
                                 saslUsername='fido-test', saslPassword=sasl_password), \
                harness.capture_logs(logging.DEBUG) as logs:
            await bot._send_oper()
            await bot._send_sasl_plain()
        self.assertEqual(bot.lines, [])
        self.assertTrue(self.logged_in(logs, f'{self.NOT_SENT} OPER'))
        self.assertTrue(self.logged_in(logs, f'{self.NOT_SENT} AUTHENTICATE'))
        sasl_secret = base64.b64encode(f"\0fido-test\0{sasl_password}".encode('utf-8')).decode('ascii')
        for secret in (oper_password, sasl_password, sasl_secret):
            self.assertFalse(self.logged_in(logs, secret), "a dropped credential write logged its secret")


class FakeBotReceiveTest(unittest.IsolatedAsyncioTestCase):
    """harness.FakeBot.receive fails the test when a handler raises; pydle itself only logs it."""

    LINE = f":{MEMBER}!jameson@192.0.2.10 PRIVMSG #ratchat :hello"

    async def test_a_handler_exception_fails_the_receive(self):
        bot = harness.FakeBot()
        with mock.patch.object(bot, 'on_raw_privmsg', side_effect=KeyError('#ratchat')), \
                harness.capture_logs(logging.DEBUG):
            with self.assertRaisesRegex(AssertionError, "a pydle handler raised KeyError: '#ratchat'"):
                await bot.receive(self.LINE)

    async def test_a_handler_that_returns_passes(self):
        bot = harness.FakeBot()
        with mock.patch.object(bot, 'on_raw_privmsg') as handler:
            await bot.receive(self.LINE)
        handler.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()

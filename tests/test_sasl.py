"""
SASL PLAIN login to FIDO's services account (D15-D17): CAP LS continuation, the sasl-only
request, the PLAIN response outside pydle's send log, the 9xx numerics, the client-side timeout,
CAP NEW after registration and the forced rename. Run as real FIDO sessions against
tests/fake_ircd.py, plus pydle-level checks on harness.FakeBot. Synthetic values only.
"""
import asyncio
import base64
import logging
import secrets
import unittest
from unittest import mock

import fido
from config import IRC
from tests import harness
from tests.fake_ircd import (CAP_LS_WITH_SASL, CAP_LS_WITHOUT_SASL, CLIENT, SASL_TOKEN, SERVER, SERVER_NAME)
from tests.test_runtime import EXIT_WITHIN, SessionTestCase

ACCOUNT = harness.BOT_NICK
FORCED_NICK = 'rat_1234'
BACKOFF = 1.0  # seconds, the lowered OPER_FAIL_BACKOFF
TIMEOUT = 0.3  # seconds, the lowered SASL_TIMEOUT
SLACK = 0.1  # seconds of timer jitter allowed
AT_ONCE = 1.0  # seconds an immediate exit may take
CHUNK = 400
# A capability UnrealIRCd 6.2.6 can announce with CAP NEW in the middle of FIDO's SASL exchange.
MULTILINE_TOKEN = 'draft/multiline=max-bytes=5250,max-lines=15'


def plain_response(account: str, password: str) -> str:
    return base64.b64encode(f"\0{account}\0{password}".encode('utf-8')).decode('ascii')


def password_for(message_bytes: int) -> str:
    """A password that makes the PLAIN message ('\\0account\\0password') exactly message_bytes long."""
    return secrets.token_urlsafe(message_bytes)[:message_bytes - len(ACCOUNT.encode()) - 2]


def requested_caps(line: str) -> list:
    """The capabilities of a 'CAP REQ' line, in either wire form ('CAP REQ sasl' or 'CAP REQ :sasl')."""
    return line.split(' ', 2)[2].lstrip(':').split()


class SASLSessionTestCase(SessionTestCase):
    def setUp(self):
        super().setUp()
        self.sasl_password = secrets.token_urlsafe(24)

    def configure(self, port, **overrides):
        settings = dict(saslUsername='', saslPassword='')
        settings.update(overrides)
        super().configure(port, **settings)

    async def sasl_session(self, cap_ls=CAP_LS_WITH_SASL, accepted=None, answers=True, cap_new_in_sasl=None,
                           **overrides):
        """
        A session with FIDO's SASL credentials set. The fake ircd accepts the password `accepted`
        (default: the configured one) and, with answers=False, never answers AUTHENTICATE PLAIN.
        cap_new_in_sasl: caps the fake ircd announces with CAP NEW between the PLAIN response and 900.
        """
        ircd = await self.start_ircd()
        ircd.cap_ls = cap_ls
        ircd.sasl_accounts = {ACCOUNT: self.sasl_password if accepted is None else accepted}
        ircd.sasl_answers = answers
        ircd.cap_new_in_sasl = cap_new_in_sasl
        settings = dict(saslUsername=ACCOUNT, saslPassword=self.sasl_password)
        settings.update(overrides)
        self.configure(ircd.port, **settings)
        client, task = await self.start_session()
        return ircd, client, task

    async def shutdown(self, client, task):
        client.request_shutdown()
        self.assertEqual((await self.exit_code(task))[0], fido.EXIT_OK)

    async def settled(self, ircd, client):
        """
        Wait until FIDO is opered and pydle's 001 handling is over. That handling ends with a WHOIS
        of FIDO's own nick, and FIDO's nick check at 001 runs after the reply, so a rename or a
        shutdown before then races it.
        """
        await self.wait_until(lambda: client.opered)
        await ircd.wait_for_line(f"WHOIS {ACCOUNT}")
        await self.sync(ircd, 'settled-1')
        await self.sync(ircd, 'settled-2')

    def assert_never_logged(self, *values):
        """None of the values appears in any record, formatted, in its msg or in its args."""
        self.assertTrue(values)
        for record in self.logs.records:
            for value in values:
                self.assertNotIn(value, self.logs.format(record))
                self.assertNotIn(value, repr(record.args))
                self.assertNotIn(value, str(record.msg))

    def secret_values(self, password=None) -> list:
        password = password or self.sasl_password
        response = plain_response(ACCOUNT, password)
        pieces = [response[start:start + CHUNK] for start in range(0, len(response), CHUNK)]
        return [password, response, base64.b64encode(password.encode()).decode(), *pieces]


class CapLsContinuationTest(SASLSessionTestCase):
    async def test_sasl_on_the_first_line_is_requested_alone_and_cap_end_waits_for_903(self):
        ircd, client, task = await self.sasl_session()
        await self.settled(ircd, client)

        requests = self.sent(ircd, 'CAP REQ')
        self.assertEqual([requested_caps(line) for line in requests], [['sasl']])
        cap_end = self.index(ircd, CLIENT, lambda line: line == 'CAP END')
        self.assertLess(self.index(ircd, SERVER, self.numeric('903')), cap_end)
        self.assertLess(cap_end, self.index(ircd, SERVER, self.numeric('001')))
        self.assertLess(self.index(ircd, CLIENT, lambda line: line == 'AUTHENTICATE PLAIN'), cap_end)
        self.assertEqual(ircd.received.count('CAP END'), 1)
        self.assertTrue(self.logged(f'SASL logged in as {ACCOUNT}'))
        await self.shutdown(client, task)

    async def test_cap_new_without_sasl_during_the_exchange_neither_warns_nor_ends_negotiation(self):
        ircd, client, task = await self.sasl_session(cap_new_in_sasl=MULTILINE_TOKEN)
        await self.settled(ircd, client)

        # The scenario: CAP NEW came after the PLAIN response and before 900.
        cap_new = self.index(ircd, SERVER, lambda line: f' NEW :{MULTILINE_TOKEN}' in line)
        response = plain_response(ACCOUNT, self.sasl_password)
        self.assertLess(self.index(ircd, CLIENT, lambda line: line == f'AUTHENTICATE {response}'), cap_new)
        self.assertLess(cap_new, self.index(ircd, SERVER, self.numeric('900')))
        self.assertEqual(ircd.received.count('CAP END'), 1)
        self.assertLess(self.index(ircd, SERVER, self.numeric('903')),
                        self.index(ircd, CLIENT, lambda line: line == 'CAP END'))
        self.assertEqual([requested_caps(line) for line in self.sent(ircd, 'CAP REQ')], [['sasl']])
        self.assertEqual([record.getMessage() for record in self.logs.records if record.levelno >= logging.WARNING],
                         [])
        self.assertTrue(self.logged(f'SASL logged in as {ACCOUNT}'))
        await self.shutdown(client, task)

    async def test_cap_end_waits_for_904_then_the_backoff_ends_the_session(self):
        self.enterContext(mock.patch.object(fido, 'OPER_FAIL_BACKOFF', BACKOFF))
        ircd, client, task = await self.sasl_session(accepted=secrets.token_urlsafe(24))
        await ircd.wait_for_line('AUTHENTICATE ' + plain_response(ACCOUNT, self.sasl_password))
        loop = asyncio.get_running_loop()
        sent_at = loop.time()
        await self.settled(ircd, client)  # registration finished and FIDO opered

        cap_end = self.index(ircd, CLIENT, lambda line: line == 'CAP END')
        self.assertLess(self.index(ircd, SERVER, self.numeric('904')), cap_end)
        self.assertLess(cap_end, self.index(ircd, SERVER, self.numeric('001')))
        self.assertFalse(task.done())
        code = await asyncio.wait_for(task, EXIT_WITHIN)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertGreaterEqual(loop.time() - sent_at, BACKOFF - SLACK)
        self.assertTrue(any(record.levelno == logging.ERROR and 'SASL failed (904' in record.getMessage()
                            for record in self.logs.records))
        self.assertEqual(self.sent(ircd, 'AUTHENTICATE *'), [])
        self.assert_never_logged(*self.secret_values())


class ResponseTest(SASLSessionTestCase):
    async def test_payload_reaches_the_server_and_no_log_record(self):
        ircd, client, task = await self.sasl_session()
        await self.settled(ircd, client)
        await self.shutdown(client, task)

        expected = plain_response(ACCOUNT, self.sasl_password)
        self.assertEqual(ircd.sasl_responses, [f"\0{ACCOUNT}\0{self.sasl_password}".encode()])
        self.assertEqual(self.sent(ircd, 'AUTHENTICATE '), ['AUTHENTICATE PLAIN', f'AUTHENTICATE {expected}'])
        # Positive controls: pydle's DEBUG send log was captured, and FIDO's own lines name the account only.
        rendered = self.logs.rendered()
        self.assertTrue(any('>> AUTHENTICATE PLAIN' in line for line in rendered))
        self.assertTrue(self.logged(f'SASL PLAIN response sent for {ACCOUNT}'))
        self.assertTrue(self.logged(f'SASL logged in as {ACCOUNT}'))
        self.assert_never_logged(*self.secret_values())

    async def test_450_byte_credential_goes_in_two_chunks(self):
        self.sasl_password = password_for(450)
        ircd, client, task = await self.sasl_session()
        await self.settled(ircd, client)
        await self.shutdown(client, task)

        expected = plain_response(ACCOUNT, self.sasl_password)
        self.assertEqual(len(expected), 600)
        self.assertEqual(self.sent(ircd, 'AUTHENTICATE '),
                         ['AUTHENTICATE PLAIN', f'AUTHENTICATE {expected[:CHUNK]}', f'AUTHENTICATE {expected[CHUNK:]}'])
        self.assertEqual(ircd.sasl_responses, [f"\0{ACCOUNT}\0{self.sasl_password}".encode()])
        self.assert_never_logged(*self.secret_values())

    async def test_a_response_of_exactly_400_bytes_ends_with_an_empty_line(self):
        self.sasl_password = password_for(300)
        ircd, client, task = await self.sasl_session()
        await self.settled(ircd, client)
        await self.shutdown(client, task)

        expected = plain_response(ACCOUNT, self.sasl_password)
        self.assertEqual(len(expected), CHUNK)
        self.assertEqual(self.sent(ircd, 'AUTHENTICATE '),
                         ['AUTHENTICATE PLAIN', f'AUTHENTICATE {expected}', 'AUTHENTICATE +'])
        self.assertEqual(ircd.sasl_responses, [f"\0{ACCOUNT}\0{self.sasl_password}".encode()])


class AbortAndTimeoutTest(SASLSessionTestCase):
    async def test_906_lets_registration_finish_and_fido_opers(self):
        ircd, client, task = await self.sasl_session(answers=False)
        await ircd.wait_for_line('AUTHENTICATE PLAIN')
        await self.sync(ircd, 'before-906')
        self.assertNotIn('CAP END', ircd.received)
        await ircd.send(f":{SERVER_NAME} 906 {ACCOUNT} :SASL authentication aborted")
        await self.settled(ircd, client)

        self.assertLess(self.index(ircd, SERVER, self.numeric('906')),
                        self.index(ircd, CLIENT, lambda line: line == 'CAP END'))
        self.assertTrue(any(record.levelno == logging.WARNING and 'SASL aborted (906)' in record.getMessage()
                            for record in self.logs.records))
        self.assertFalse(task.done())
        await self.shutdown(client, task)

    async def test_905_backs_off_then_exits_1(self):
        self.enterContext(mock.patch.object(fido, 'OPER_FAIL_BACKOFF', BACKOFF))
        ircd, client, task = await self.sasl_session(answers=False)
        await ircd.wait_for_line('AUTHENTICATE PLAIN')
        await ircd.send(f":{SERVER_NAME} 905 {ACCOUNT} :SASL message too long")
        await self.settled(ircd, client)
        code = await asyncio.wait_for(task, EXIT_WITHIN)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertTrue(self.logged('SASL failed (905'))

    async def test_no_reply_times_out_aborts_and_exits_after_the_backoff(self):
        self.enterContext(mock.patch.object(fido, 'OPER_FAIL_BACKOFF', BACKOFF))
        self.enterContext(mock.patch.object(fido, 'SASL_TIMEOUT', TIMEOUT))
        ircd, client, task = await self.sasl_session(answers=False)
        await ircd.wait_for_line('AUTHENTICATE PLAIN')
        loop = asyncio.get_running_loop()
        started = loop.time()
        await ircd.wait_for_line('AUTHENTICATE *')
        self.assertGreaterEqual(loop.time() - started, TIMEOUT - SLACK)
        await self.settled(ircd, client)

        abort = self.index(ircd, CLIENT, lambda line: line == 'AUTHENTICATE *')
        self.assertLess(abort, self.index(ircd, CLIENT, lambda line: line == 'CAP END'))
        self.assertEqual(ircd.received.count('CAP END'), 1)  # the 906 answering the abort ends nothing twice
        code = await asyncio.wait_for(task, EXIT_WITHIN)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertGreaterEqual(loop.time() - started, TIMEOUT + BACKOFF - SLACK)
        self.assertTrue(any(record.levelno == logging.ERROR and f'SASL failed (no reply within {TIMEOUT} s)'
                            in record.getMessage() for record in self.logs.records))
        self.assertEqual(ircd.sasl_responses, [])
        self.assert_never_logged(self.sasl_password, plain_response(ACCOUNT, self.sasl_password))


class CapNewTest(SASLSessionTestCase):
    async def test_services_down_at_connect_then_cap_new_logs_in_once(self):
        ircd, client, task = await self.sasl_session(cap_ls=CAP_LS_WITHOUT_SASL)
        await self.settled(ircd, client)
        self.assertEqual(self.sent(ircd, 'CAP REQ'), [])
        self.assertEqual(self.sent(ircd, 'AUTHENTICATE'), [])
        self.assertTrue(self.logged('The server offers no SASL'))

        await ircd.cap_new(SASL_TOKEN)
        await self.wait_until(lambda: self.logged(f'SASL logged in as {ACCOUNT}'))
        await self.sync(ircd, 'after-login')
        self.assertEqual([requested_caps(line) for line in self.sent(ircd, 'CAP REQ')], [['sasl']])
        self.assertEqual(self.sent(ircd, 'AUTHENTICATE PLAIN'), ['AUTHENTICATE PLAIN'])

        await ircd.cap_del('sasl')
        await ircd.cap_new(SASL_TOKEN)
        await self.sync(ircd, 'after-relink')
        self.assertEqual(len(self.sent(ircd, 'CAP REQ')), 1)
        self.assertEqual(self.sent(ircd, 'AUTHENTICATE PLAIN'), ['AUTHENTICATE PLAIN'])
        self.assertFalse(task.done())
        await self.shutdown(client, task)

    async def test_cap_new_without_sasl_after_registration_sends_nothing(self):
        ircd, client, task = await self.sasl_session()
        await self.settled(ircd, client)
        before = len(ircd.received)
        await ircd.cap_new(MULTILINE_TOKEN)
        await self.sync(ircd, 'after-cap-new')
        self.assertEqual([line for line in ircd.received[before:] if not line.startswith('PONG ')], [])
        self.assertEqual([record.getMessage() for record in self.logs.records if record.levelno >= logging.WARNING],
                         [])
        await self.shutdown(client, task)

    async def test_cap_del_and_new_after_a_login_at_connect_send_no_second_authenticate(self):
        ircd, client, task = await self.sasl_session()
        await self.settled(ircd, client)
        await ircd.cap_del('sasl')
        await ircd.cap_new(SASL_TOKEN)
        await self.sync(ircd, 'after-relink')
        self.assertEqual(len(self.sent(ircd, 'CAP REQ')), 1)
        self.assertEqual(self.sent(ircd, 'AUTHENTICATE PLAIN'), ['AUTHENTICATE PLAIN'])
        self.assertFalse(task.done())
        await self.shutdown(client, task)


class NoLoginTest(SASLSessionTestCase):
    async def test_no_credentials_send_no_authenticate(self):
        ircd = await self.start_ircd()
        ircd.cap_ls = CAP_LS_WITH_SASL
        self.configure(ircd.port)
        client, task = await self.start_session()
        await self.settled(ircd, client)
        self.assertEqual(self.sent(ircd, 'CAP REQ'), [])
        self.assertEqual(self.sent(ircd, 'AUTHENTICATE'), [])
        self.assertLess(self.index(ircd, CLIENT, lambda line: line == 'CAP END'),
                        self.index(ircd, SERVER, self.numeric('001')))
        self.assertFalse(self.logged('SASL'))
        await self.shutdown(client, task)

    async def test_sasl_without_plain_is_not_requested(self):
        cap_ls = (CAP_LS_WITHOUT_SASL[0] + ' sasl=EXTERNAL', CAP_LS_WITHOUT_SASL[1])
        ircd, client, task = await self.sasl_session(cap_ls=cap_ls)
        await self.settled(ircd, client)
        self.assertEqual(self.sent(ircd, 'CAP REQ'), [])
        self.assertEqual(self.sent(ircd, 'AUTHENTICATE'), [])
        self.assertTrue(any(record.levelno == logging.WARNING and 'without PLAIN (external)' in record.getMessage()
                            for record in self.logs.records))
        await self.shutdown(client, task)


class ForcedRenameTest(SASLSessionTestCase):
    async def test_forced_rename_exits_1_at_once(self):
        ircd, client, task = await self.sasl_session()
        await self.settled(ircd, client)
        await ircd.force_nick(FORCED_NICK)
        code, elapsed = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertLess(elapsed, AT_ONCE)
        self.assertTrue(self.logged(f'renamed from {ACCOUNT} to {FORCED_NICK} by the server'))

    async def test_forced_rename_during_a_sasl_backoff_waits_for_it(self):
        self.enterContext(mock.patch.object(fido, 'OPER_FAIL_BACKOFF', BACKOFF))
        ircd, client, task = await self.sasl_session(accepted=secrets.token_urlsafe(24))
        await ircd.wait_for_line('AUTHENTICATE ' + plain_response(ACCOUNT, self.sasl_password))
        loop = asyncio.get_running_loop()
        sent_at = loop.time()
        await self.settled(ircd, client)
        await ircd.force_nick(FORCED_NICK)
        code = await asyncio.wait_for(task, EXIT_WITHIN)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertGreaterEqual(loop.time() - sent_at, BACKOFF - SLACK)

    async def test_another_users_rename_is_not_fidos(self):
        ircd, client, task = await self.sasl_session()
        await self.settled(ircd, client)
        await ircd.send(f":{harness.USER_NICK}!jameson@{SERVER_NAME} NICK :{FORCED_NICK}")
        await self.sync(ircd, 'after-rename')
        self.assertFalse(task.done())
        await self.shutdown(client, task)


class RegisteredLoginTest(unittest.IsolatedAsyncioTestCase):
    """CAP NEW sasl after registration, on a FakeBot: the exchange ends without CAP END."""

    async def test_login_after_registration_sends_no_cap_end(self):
        password = secrets.token_urlsafe(24)
        self.enterContext(mock.patch.multiple(IRC, saslUsername=ACCOUNT, saslPassword=password))
        bot = harness.FakeBot()
        prefix = f":{SERVER_NAME}"
        await bot.receive(f"{prefix} CAP {ACCOUNT} NEW :{SASL_TOKEN}")
        self.assertEqual(bot.lines, ['CAP REQ sasl'])
        await bot.receive(f"{prefix} CAP {ACCOUNT} ACK :sasl")
        self.assertEqual(bot.lines[-1], 'AUTHENTICATE PLAIN')
        await bot.receive('AUTHENTICATE +')
        self.assertEqual(bot.lines[-1], f'AUTHENTICATE {plain_response(ACCOUNT, password)}')
        await bot.receive(f"{prefix} 900 {ACCOUNT} {ACCOUNT}!fido@{SERVER_NAME} {ACCOUNT} "
                          f":You are now logged in as {ACCOUNT}")
        await bot.receive(f"{prefix} 903 {ACCOUNT} :SASL authentication successful")
        self.assertNotIn('CAP END', bot.lines)
        self.assertNotIn('sasl', bot._capabilities_negotiating)
        self.assertIsNone(bot._sasl_deadline)


if __name__ == '__main__':
    unittest.main()

"""
The exit contract, the OPER line, shutdown and TLS verification, each run as a real FIDO session
against tests/fake_ircd.py in this process.
"""
import asyncio
import contextlib
import logging
import os
import secrets
import signal
import socket
import ssl
import subprocess
import tempfile
import unittest
from unittest import mock

import fido
from config import IRC
from tests import harness
from tests.fake_ircd import FakeIRCd, SERVER_NAME, DEFAULT_SNOMASK

RUN_TIMEOUT = 10  # seconds a session may take in any test
EXIT_WITHIN = 5  # seconds an expected exit may take
SHUTDOWN_WITHIN = 4  # seconds from SIGTERM to exit 0
OPER_NAME = 'fido-test'
SILENCE_LIMIT = 1  # seconds, the lowered FIDO_SILENCE_LIMIT of the keep-alive test
LINE_INTERVAL = 0.3  # seconds between two server lines in that test
KEPT_ALIVE_FOR = 2.5  # seconds the server keeps sending lines in that test
SILENCE_SLACK = 0.1  # seconds of timer jitter allowed


def quit_reason(line: str):
    """The reason of a QUIT line, or None for any other line."""
    command, _, rest = line.partition(' ')
    return rest.lstrip(':') if command == 'QUIT' else None


class SessionTestCase(unittest.IsolatedAsyncioTestCase):
    """Runs fido.FIDO.run_session() against a FakeIRCd, with settings patched on config.IRC."""

    def setUp(self):
        self.db = self.enterContext(harness.TempDB())
        self.password = secrets.token_urlsafe(18)
        self.logs = self.enterContext(harness.capture_logs(logging.DEBUG))

    def configure(self, port, **overrides):
        settings = dict(server='127.0.0.1', port=port, useSsl=False, tlsVerify=False, tlsServerName='',
                        nickname=harness.BOT_NICK, operline=OPER_NAME, operlinePassword=self.password,
                        expectSnomask='', startupDeadline=EXIT_WITHIN, silenceLimit=RUN_TIMEOUT * 3)
        settings.update(overrides)
        self.enterContext(mock.patch.multiple(IRC, **settings))

    async def start_ircd(self, **kwargs) -> FakeIRCd:
        ircd = FakeIRCd(**kwargs)
        await ircd.start()
        self.addAsyncCleanup(ircd.stop)
        return ircd

    async def start_session(self):
        client = fido.FIDO(IRC.nickname)
        task = asyncio.create_task(client.run_session())
        self.addAsyncCleanup(self._cancel, task)
        return client, task

    @staticmethod
    async def _cancel(task):
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @staticmethod
    async def wait_until(predicate, timeout=EXIT_WITHIN):
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(0.01)

    async def exit_code(self, task, timeout=EXIT_WITHIN):
        """The session's exit code and how long it took to arrive."""
        loop = asyncio.get_running_loop()
        start = loop.time()
        code = await asyncio.wait_for(task, timeout)
        return code, loop.time() - start

    def logged(self, text: str) -> bool:
        return any(text in message for message in self.logs.messages())

    @staticmethod
    async def sync(ircd, marker: str):
        """Wait until FIDO has handled every line sent before this: it answers PING in order."""
        await ircd.send(f"PING :{marker}")
        await ircd.wait_for_line(f"PONG {marker}")

    @staticmethod
    def index(ircd, direction: str, predicate) -> int:
        """Position in the transcript of the first line from direction that matches predicate."""
        for position, (who, line) in enumerate(ircd.transcript):
            if who == direction and predicate(line):
                return position
        raise AssertionError(f"no {direction} line matched in {ircd.transcript!r}")

    @staticmethod
    def numeric(code: str):
        return lambda line: line.split(' ')[1:2] == [code]

    @staticmethod
    def sent(ircd, prefix: str) -> list:
        return [line for line in ircd.received if line.startswith(prefix)]

    async def opered_session(self, ircd=None, **overrides):
        ircd = ircd or await self.start_ircd()
        self.configure(ircd.port, **overrides)
        client, task = await self.start_session()
        await self.wait_until(lambda: client.opered)
        return ircd, client, task


class OperLineTest(SessionTestCase):
    async def test_password_reaches_the_server_and_no_log_record(self):
        ircd, client, task = await self.opered_session()
        client.request_shutdown()
        code, _ = await self.exit_code(task)

        self.assertEqual(code, fido.EXIT_OK)
        # Positive controls: the server got the password, and pydle's DEBUG send log was captured.
        self.assertEqual(await ircd.wait_for_line('OPER '), f'OPER {OPER_NAME} {self.password}')
        self.assertTrue(any(f'>> NICK {harness.BOT_NICK}' in line for line in self.logs.rendered()))
        self.assertTrue(self.logged(f'OPER sent for {OPER_NAME}'))
        for record in self.logs.records:
            self.assertNotIn(self.password, self.logs.format(record))
            self.assertNotIn(self.password, repr(record.args))
            self.assertNotIn(self.password, str(record.msg))

    async def test_opered_line_names_the_snomask(self):
        _, client, task = await self.opered_session(expectSnomask=DEFAULT_SNOMASK)
        self.assertTrue(self.logged(f'opered, snomask {DEFAULT_SNOMASK}'))
        self.assertFalse(any(record.levelno >= logging.WARNING and 'snomask' in record.getMessage()
                             for record in self.logs.records))
        client.request_shutdown()
        self.assertEqual((await self.exit_code(task))[0], fido.EXIT_OK)

    async def test_unexpected_snomask_warns_and_keeps_running(self):
        _, client, task = await self.opered_session(expectSnomask='+cC')
        self.assertTrue(any(record.levelno == logging.WARNING and 'differs from the expected +cC' in record.getMessage()
                            for record in self.logs.records))
        self.assertFalse(task.done())
        client.request_shutdown()
        self.assertEqual((await self.exit_code(task))[0], fido.EXIT_OK)


class ExitContractTest(SessionTestCase):
    async def test_clean_close_exits_1(self):
        ircd, _, task = await self.opered_session()
        await ircd.close_client()
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)

    async def test_reset_exits_1(self):
        ircd, _, task = await self.opered_session()
        await ircd.close_client(reset=True)
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)

    async def test_kill_exits_1(self):
        ircd, _, task = await self.opered_session()
        await ircd.send(f":Jameson!jameson@{SERVER_NAME} KILL {harness.BOT_NICK} :test")
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)

    async def test_silent_server_exits_at_startup_deadline(self):
        ircd = await self.start_ircd()
        ircd.register = False
        self.configure(ircd.port, startupDeadline=1)
        _, task = await self.start_session()
        code, elapsed = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertGreaterEqual(elapsed, 0.9)
        self.assertTrue(self.logged('not opered within 1 s'))

    async def test_nick_in_use_exits_1(self):
        ircd = await self.start_ircd()
        ircd.taken_nicks.add(harness.BOT_NICK)
        self.configure(ircd.port)
        _, task = await self.start_session()
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertIn(f'NICK {harness.BOT_NICK}_', ircd.received)
        self.assertTrue(self.logged(f'registered as {harness.BOT_NICK}_'))

    async def test_connection_refused_exits_1(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.configure(port)
        _, task = await self.start_session()
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertTrue(self.logged('failed'))

    async def test_silence_limit_exits_1(self):
        _, _, task = await self.opered_session(silenceLimit=1)
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertTrue(self.logged('no line received for'))

    async def test_received_lines_keep_the_session_within_the_silence_limit(self):
        ircd, _, task = await self.opered_session(silenceLimit=SILENCE_LIMIT)
        loop = asyncio.get_running_loop()
        until = loop.time() + KEPT_ALIVE_FOR
        count = 0
        while loop.time() < until:
            await ircd.send(f":{SERVER_NAME} NOTICE {harness.BOT_NICK} :line {count}")
            count += 1
            await asyncio.sleep(LINE_INTERVAL)
            self.assertFalse(task.done(), f"the session ended after {count} lines")
        code, elapsed = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertGreaterEqual(elapsed, SILENCE_LIMIT - LINE_INTERVAL - SILENCE_SLACK)
        self.assertTrue(self.logged('no line received for'))

    async def test_oper_464_waits_out_the_backoff(self):
        backoff = 1.5
        self.enterContext(mock.patch.object(fido, 'OPER_FAIL_BACKOFF', backoff))
        ircd = await self.start_ircd()
        ircd.oper_reply = '464'
        self.configure(ircd.port, startupDeadline=0.5)
        _, task = await self.start_session()
        await ircd.wait_for_line('OPER ')
        loop = asyncio.get_running_loop()
        oper_at = loop.time()
        await asyncio.sleep(0.1)
        await ircd.close_client()  # neither the read loop ending nor the startup deadline cuts the wait short
        code = await asyncio.wait_for(task, EXIT_WITHIN)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertGreaterEqual(loop.time() - oper_at, backoff - 0.1)
        self.assertTrue(self.logged('OPER failed (464'))

    async def test_oper_491_exits_1(self):
        self.enterContext(mock.patch.object(fido, 'OPER_FAIL_BACKOFF', 0.2))
        ircd = await self.start_ircd()
        ircd.oper_reply = '491'
        self.configure(ircd.port)
        _, task = await self.start_session()
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertTrue(self.logged('OPER failed (491'))

    async def test_shutdown_during_backoff_exits_0(self):
        self.enterContext(mock.patch.object(fido, 'OPER_FAIL_BACKOFF', 60))
        ircd = await self.start_ircd()
        ircd.oper_reply = '464'
        self.configure(ircd.port)
        client, task = await self.start_session()
        await ircd.wait_for_line('OPER ')
        await self.wait_until(lambda: self.logged('OPER failed'))
        client.request_shutdown()
        code, elapsed = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_OK)
        self.assertLess(elapsed, SHUTDOWN_WITHIN)


class ShutdownTest(SessionTestCase):
    async def test_sigterm_sends_quit_and_exits_0(self):
        ircd, _, task = await self.opered_session()
        os.kill(os.getpid(), signal.SIGTERM)
        code, elapsed = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_OK)
        self.assertLess(elapsed, SHUTDOWN_WITHIN)
        self.assertIn(fido.QUIT_MESSAGE, [quit_reason(line) for line in ircd.received])

    async def test_signal_handlers_are_removed_after_the_session(self):
        _, client, task = await self.opered_session()
        client.request_shutdown()
        await self.exit_code(task)
        self.assertFalse(asyncio.get_running_loop().remove_signal_handler(signal.SIGTERM))


def openssl(directory, *args):
    subprocess.run(['openssl', *args], cwd=directory, check=True, capture_output=True)


def make_ca(directory, name):
    openssl(directory, 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes',
            '-keyout', f'{name}.key', '-out', f'{name}.pem', '-days', '2', '-subj', f'/CN=FIDO test {name}',
            '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
    return os.path.join(directory, f'{name}.pem')


def make_server_cert(directory, ca_name, hostname):
    """A certificate for hostname (DNS SAN only, no IP) signed by the named CA."""
    with open(os.path.join(directory, 'server.ext'), 'w') as ext:
        ext.write('basicConstraints=CA:FALSE\n'
                  'keyUsage=critical,digitalSignature\n'
                  'extendedKeyUsage=serverAuth\n'
                  f'subjectAltName=DNS:{hostname}\n'
                  'subjectKeyIdentifier=hash\n'
                  'authorityKeyIdentifier=keyid\n')
    openssl(directory, 'req', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes',
            '-keyout', 'server.key', '-out', 'server.csr', '-subj', f'/CN={hostname}')
    openssl(directory, 'x509', '-req', '-in', 'server.csr', '-CA', f'{ca_name}.pem', '-CAkey', f'{ca_name}.key',
            '-CAcreateserial', '-days', '2', '-out', 'server.pem', '-extfile', 'server.ext')
    return os.path.join(directory, 'server.pem'), os.path.join(directory, 'server.key')


class TLSTest(SessionTestCase):
    """Certificates are made at run time: a server CA, an unrelated CA, and irc.example.test signed by the first."""

    @classmethod
    def setUpClass(cls):
        cls._certs = tempfile.TemporaryDirectory()
        directory = cls._certs.name
        cls.server_ca = make_ca(directory, 'server-ca')
        cls.other_ca = make_ca(directory, 'other-ca')
        cls.cert, cls.key = make_server_cert(directory, 'server-ca', SERVER_NAME)

    @classmethod
    def tearDownClass(cls):
        cls._certs.cleanup()

    def setUp(self):
        super().setUp()
        self.sni = []

    def server_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert, self.key)
        context.sni_callback = lambda sslobj, name, ctx: self.sni.append(name)
        return context

    def trust(self, ca_file):
        """Make ca_file the default CA file, as OpenSSL reads SSL_CERT_FILE when the context loads defaults."""
        self.enterContext(mock.patch.dict(os.environ, {'SSL_CERT_FILE': ca_file}))

    async def tls_session(self, **overrides):
        ircd = await self.start_ircd(ssl=self.server_context())
        self.configure(ircd.port, useSsl=True, **overrides)
        client, task = await self.start_session()
        return ircd, client, task

    async def test_right_ca_and_server_name_verify(self):
        self.trust(self.server_ca)
        _, client, task = await self.tls_session(tlsVerify=True, tlsServerName=SERVER_NAME)
        await self.wait_until(lambda: client.opered)
        self.assertEqual(self.sni, [SERVER_NAME])
        client.request_shutdown()
        self.assertEqual((await self.exit_code(task))[0], fido.EXIT_OK)

    async def test_wrong_ca_fails(self):
        self.trust(self.other_ca)
        ircd, _, task = await self.tls_session(tlsVerify=True, tlsServerName=SERVER_NAME)
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertTrue(self.logged('CERTIFICATE_VERIFY_FAILED'))
        self.assertEqual(ircd.received, [])

    async def test_connect_address_without_server_name_fails(self):
        self.trust(self.server_ca)
        ircd, _, task = await self.tls_session(tlsVerify=True, tlsServerName='')
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)
        self.assertTrue(self.logged('CERTIFICATE_VERIFY_FAILED'))
        self.assertEqual(ircd.received, [])

    async def test_verification_off_accepts_any_certificate(self):
        self.trust(self.other_ca)
        _, client, task = await self.tls_session(tlsVerify=False)
        await self.wait_until(lambda: client.opered)
        client.request_shutdown()
        self.assertEqual((await self.exit_code(task))[0], fido.EXIT_OK)

    async def test_reset_over_tls_exits_1(self):
        ircd, client, task = await self.tls_session(tlsVerify=False)
        await self.wait_until(lambda: client.opered)
        await ircd.close_client(reset=True)
        code, _ = await self.exit_code(task)
        self.assertEqual(code, fido.EXIT_SESSION_LOST)


if __name__ == '__main__':
    unittest.main()

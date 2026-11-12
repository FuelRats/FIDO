"""
The process contract of `python fido.py`: exit codes and their timing, SIGTERM, and no password on
stdout or stderr at DEBUG. Each case runs FIDO as a subprocess against tests/fake_ircd.py on
127.0.0.1 (plaintext, FIDO_IRC_TLS=off), with an environment holding no inherited FIDO_ or AWS_
variable, a temp DB built from prod's schema and generated dummy passwords.
"""
import asyncio
import base64
import os
import pathlib
import secrets
import signal
import socket
import sys
import tempfile
import unittest

from tests import harness
from tests.fake_ircd import CAP_LS_WITH_SASL, FakeIRCd

REPO = pathlib.Path(__file__).resolve().parent.parent
OPER_NAME = 'fido-test'
STARTUP_DEADLINE = 5  # seconds, FIDO_STARTUP_DEADLINE in every case
EXIT_WITHIN = 5  # seconds from the trigger to an expected exit 1
SHUTDOWN_WITHIN = 4  # seconds from SIGTERM to exit 0
OPER_BACKOFF = 1  # seconds, the lowered fido.OPER_FAIL_BACKOFF in case (f)
DEADLINE_EARLY = 0.5  # seconds the startup deadline may pass before the server sees the connection
START_TIMEOUT = 30  # seconds a child may take to import and get as far as a case needs
POLL_INTERVAL = 0.02  # seconds
CHUNK = 400  # base64 bytes per AUTHENTICATE line
# Runs main() like `python fido.py`, with the OPER back-off lowered, which no setting controls.
BACKOFF_RUNNER = ('import asyncio, sys, fido; fido.OPER_FAIL_BACKOFF = {backoff}; '
                  'sys.exit(asyncio.run(fido.main()))')


def free_port() -> int:
    """A local port with nothing listening on it."""
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class FIDOProcess:
    """One `python fido.py` (or a -c runner) whose stdout and stderr go to files."""

    def __init__(self, directory: str):
        self.stdout_path = os.path.join(directory, 'stdout.txt')
        self.stderr_path = os.path.join(directory, 'stderr.txt')
        self.proc = None
        self.started = None

    async def start(self, env: dict, *args):
        loop = asyncio.get_running_loop()
        with open(self.stdout_path, 'wb') as stdout, open(self.stderr_path, 'wb') as stderr:
            self.proc = await asyncio.create_subprocess_exec(sys.executable, *(args or ('fido.py',)), cwd=REPO,
                                                             env=env, stdout=stdout, stderr=stderr)
        self.started = loop.time()

    def stdout(self) -> str:
        return pathlib.Path(self.stdout_path).read_text(errors='replace')

    def stderr(self) -> str:
        return pathlib.Path(self.stderr_path).read_text(errors='replace')

    async def wait_for_output(self, text: str, timeout=START_TIMEOUT):
        """Wait until stdout contains text; fail early if the process exits first."""
        async with asyncio.timeout(timeout):
            while text not in self.stdout():
                if self.proc.returncode is not None:
                    raise AssertionError(f"exited with {self.proc.returncode} before logging {text!r}")
                await asyncio.sleep(POLL_INTERVAL)

    async def exit_code(self, timeout, since=None):
        """The exit code and the seconds from since (default: the start) to the exit."""
        loop = asyncio.get_running_loop()
        code = await asyncio.wait_for(self.proc.wait(), timeout)
        return code, loop.time() - (self.started if since is None else since)

    async def kill(self):
        if self.proc is not None and self.proc.returncode is None:
            self.proc.kill()
            await self.proc.wait()


class ProcessTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = self.enterContext(tempfile.TemporaryDirectory())
        db = os.path.join(self.dir, 'FIDO.sqlite')
        harness.build_db(db)
        self.db_url = f'sqlite:///{db}'
        self.password = secrets.token_urlsafe(18)

    def env(self, port: int, **overrides) -> dict:
        env = {name: value for name, value in os.environ.items() if not name.startswith(('FIDO_', 'AWS_'))}
        env.update(PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1', FIDO_IRC_SERVER='127.0.0.1',
                   FIDO_IRC_PORT=str(port), FIDO_IRC_TLS='off', FIDO_OPER_NAME=OPER_NAME,
                   FIDO_OPER_PASSWORD=self.password, FIDO_DB_URL=self.db_url,
                   FIDO_STARTUP_DEADLINE=str(STARTUP_DEADLINE), FIDO_LOG_LEVEL='INFO')
        env.update(overrides)
        return env

    async def start_ircd(self) -> FakeIRCd:
        ircd = FakeIRCd()
        await ircd.start()
        self.addAsyncCleanup(ircd.stop)
        return ircd

    async def start_fido(self, env: dict, *args) -> FIDOProcess:
        fido = FIDOProcess(self.dir)
        await fido.start(env, *args)
        self.addAsyncCleanup(fido.kill)
        return fido

    async def opered(self, fido: FIDOProcess, ircd: FakeIRCd):
        """
        Wait until FIDO is opered and pydle's 001 handling is over: it ends with a WHOIS of FIDO's
        own nick, and two PING round trips after that one ensure FIDO has handled its reply.
        """
        await fido.wait_for_output('opered, snomask')
        await ircd.wait_for_line(f'WHOIS {harness.BOT_NICK}')
        for marker in ('settled-1', 'settled-2'):
            await ircd.send(f'PING :{marker}')
            await ircd.wait_for_line(f'PONG {marker}')

    async def wait_for_connection(self, ircd: FakeIRCd) -> float:
        """The loop time at which the fake server has accepted FIDO's connection."""
        async with asyncio.timeout(START_TIMEOUT):
            while ircd.connections == 0:
                await asyncio.sleep(POLL_INTERVAL)
        return asyncio.get_running_loop().time()

    def assert_no_traceback(self, fido: FIDOProcess):
        self.assertNotIn('Traceback', fido.stdout())
        self.assertNotIn('Traceback', fido.stderr())

    def assert_absent(self, fido: FIDOProcess, *values):
        """None of the values appears on stdout or stderr."""
        self.assertTrue(values)
        output = fido.stdout() + fido.stderr()
        for value in values:
            self.assertNotIn(value, output)

    async def sigterm(self, fido: FIDOProcess, ircd: FakeIRCd):
        """SIGTERM: FIDO sends QUIT with its reason and exits 0 within SHUTDOWN_WITHIN."""
        loop = asyncio.get_running_loop()
        fido.proc.send_signal(signal.SIGTERM)
        code, elapsed = await fido.exit_code(SHUTDOWN_WITHIN + 1, since=loop.time())
        self.assertEqual(code, 0)
        self.assertLess(elapsed, SHUTDOWN_WITHIN)
        self.assertIn('QUIT restarting', ircd.received)


class ExitTest(ProcessTestCase):
    async def test_a_nothing_listening_exits_1_within_the_startup_deadline(self):
        port = free_port()
        fido = await self.start_fido(self.env(port))
        code, elapsed = await fido.exit_code(START_TIMEOUT)
        self.assertEqual(code, 1)
        self.assertLess(elapsed, STARTUP_DEADLINE)
        self.assertIn(f'connect to 127.0.0.1:{port} failed', fido.stdout())
        self.assert_no_traceback(fido)

    async def test_b_clean_close_after_oper_exits_1(self):
        ircd = await self.start_ircd()
        fido = await self.start_fido(self.env(ircd.port))
        await self.opered(fido, ircd)
        closed_at = asyncio.get_running_loop().time()
        await ircd.close_client()
        code, elapsed = await fido.exit_code(EXIT_WITHIN + 1, since=closed_at)
        self.assertEqual(code, 1)
        self.assertLess(elapsed, EXIT_WITHIN)
        self.assert_no_traceback(fido)

    async def test_c_reset_after_oper_exits_1(self):
        ircd = await self.start_ircd()
        fido = await self.start_fido(self.env(ircd.port))
        await self.opered(fido, ircd)
        reset_at = asyncio.get_running_loop().time()
        await ircd.close_client(reset=True)
        code, elapsed = await fido.exit_code(EXIT_WITHIN + 1, since=reset_at)
        self.assertEqual(code, 1)
        self.assertLess(elapsed, EXIT_WITHIN)
        self.assert_no_traceback(fido)

    async def test_d_silent_server_exits_1_at_the_startup_deadline(self):
        ircd = await self.start_ircd()
        ircd.register = False
        fido = await self.start_fido(self.env(ircd.port))
        accepted_at = await self.wait_for_connection(ircd)
        code, elapsed = await fido.exit_code(STARTUP_DEADLINE + EXIT_WITHIN, since=accepted_at)
        self.assertEqual(code, 1)
        self.assertGreaterEqual(elapsed, STARTUP_DEADLINE - DEADLINE_EARLY)
        self.assertLess(elapsed, STARTUP_DEADLINE + EXIT_WITHIN)
        self.assertIn(f'not opered within {STARTUP_DEADLINE} s', fido.stdout())
        self.assert_no_traceback(fido)

    async def test_e_nick_in_use_registers_with_an_underscore_and_exits_1(self):
        ircd = await self.start_ircd()
        ircd.taken_nicks.add(harness.BOT_NICK)
        fido = await self.start_fido(self.env(ircd.port))
        accepted_at = await self.wait_for_connection(ircd)
        code, elapsed = await fido.exit_code(EXIT_WITHIN + 1, since=accepted_at)
        self.assertEqual(code, 1)
        self.assertLess(elapsed, EXIT_WITHIN)
        self.assertIn(f'NICK {harness.BOT_NICK}_', ircd.received)
        self.assertIn(f'registered as {harness.BOT_NICK}_', fido.stdout())
        self.assert_no_traceback(fido)

    async def test_f_oper_464_exits_1_after_the_backoff(self):
        ircd = await self.start_ircd()
        ircd.oper_reply = '464'
        fido = await self.start_fido(self.env(ircd.port), '-c', BACKOFF_RUNNER.format(backoff=OPER_BACKOFF))
        await ircd.wait_for_line('OPER ', timeout=START_TIMEOUT)
        oper_at = asyncio.get_running_loop().time()
        code, elapsed = await fido.exit_code(OPER_BACKOFF + EXIT_WITHIN, since=oper_at)
        self.assertEqual(code, 1)
        self.assertGreaterEqual(elapsed, OPER_BACKOFF - 0.1)
        self.assertLess(elapsed, OPER_BACKOFF + EXIT_WITHIN)
        self.assertIn('OPER failed (464 password mismatch)', fido.stdout())
        self.assert_no_traceback(fido)

    async def test_i_unparsable_values_exit_2_with_one_line_and_no_traceback(self):
        for name, value, problem in (('FIDO_IRC_PORT', 'abc', 'FIDO_IRC_PORT must be an integer'),
                                     ('FIDO_IRC_TLS', 'sometimes', 'FIDO_IRC_TLS must be one of')):
            with self.subTest(name=name):
                fido = await self.start_fido(self.env(free_port(), **{name: value}))
                code, _ = await fido.exit_code(START_TIMEOUT)
                self.assertEqual(code, 2)
                self.assertEqual(fido.stderr(), '')
                lines = fido.stdout().splitlines()
                self.assertEqual(len(lines), 1, lines)
                self.assertTrue(lines[0].startswith('CRITICAL:'), lines)
                self.assertIn(f'Configuration error: {problem}', lines[0])


class ShutdownTest(ProcessTestCase):
    async def test_g_sigterm_sends_quit_and_exits_0(self):
        ircd = await self.start_ircd()
        fido = await self.start_fido(self.env(ircd.port))
        await self.opered(fido, ircd)
        await self.sigterm(fido, ircd)
        self.assert_no_traceback(fido)


class NoPasswordOutputTest(ProcessTestCase):
    async def test_h_oper_password_is_not_on_stdout_or_stderr_at_debug(self):
        ircd = await self.start_ircd()
        fido = await self.start_fido(self.env(ircd.port, FIDO_LOG_LEVEL='DEBUG'))
        await self.opered(fido, ircd)
        await self.sigterm(fido, ircd)
        # Positive controls: the server got the password, and pydle's DEBUG send log is on stdout.
        self.assertIn(f'OPER {OPER_NAME} {self.password}', ircd.received)
        self.assertIn(f'>> NICK {harness.BOT_NICK}', fido.stdout())
        self.assertIn(f'OPER sent for {OPER_NAME}', fido.stdout())
        self.assert_absent(fido, self.password)
        self.assert_no_traceback(fido)

    async def test_j_sasl_password_is_not_on_stdout_or_stderr_at_debug(self):
        sasl_password = secrets.token_urlsafe(24)
        ircd = await self.start_ircd()
        ircd.cap_ls = CAP_LS_WITH_SASL
        ircd.sasl_accounts = {harness.BOT_NICK: sasl_password}
        fido = await self.start_fido(self.env(ircd.port, FIDO_LOG_LEVEL='DEBUG', FIDO_SASL_USERNAME=harness.BOT_NICK,
                                              FIDO_SASL_PASSWORD=sasl_password))
        await self.opered(fido, ircd)
        await self.sigterm(fido, ircd)
        plain = f'\0{harness.BOT_NICK}\0{sasl_password}'.encode()
        response = base64.b64encode(plain).decode('ascii')
        # Positive controls: the server decoded exactly this login, and the exchange is in the DEBUG log.
        self.assertEqual(ircd.sasl_responses, [plain])
        self.assertIn('>> AUTHENTICATE PLAIN', fido.stdout())
        self.assertIn(f'SASL PLAIN response sent for {harness.BOT_NICK}', fido.stdout())
        self.assertIn(f'SASL logged in as {harness.BOT_NICK}', fido.stdout())
        pieces = [response[start:start + CHUNK] for start in range(0, len(response), CHUNK)]
        self.assert_absent(fido, sasl_password, response, base64.b64encode(sasl_password.encode()).decode(),
                           *pieces, self.password)
        self.assert_no_traceback(fido)


if __name__ == '__main__':
    unittest.main()

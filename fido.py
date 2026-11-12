import asyncio
import logging
import signal
import sys

import pydle
import pydle.connection
import pydle.protocol

from config import IRC, Logging
from models import monitor, session_scope
from modules import noticehandler, channelprotectionhandler
from modules import commandhandler as commandHandler
from modules import access, configmanager
from modules.newrats import induction

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_SESSION_LOST = 1
EXIT_CONFIG = 2

OPER_FAIL_BACKOFF = 300  # seconds between a 464/491 and the exit; read at use time, tests lower it
SHUTDOWN_GRACE = 3  # seconds to wait for the server to close the link after QUIT
WATCHDOG_INTERVAL = 5  # longest pause between two silence checks, in seconds
QUIT_MESSAGE = 'restarting'


class ServerNameConnection(pydle.connection.Connection):
    """pydle Connection that verifies TLS against, and sends as SNI, a name other than the host it connects to."""

    def __init__(self, *args, server_hostname=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.server_hostname = server_hostname or None

    async def connect(self):
        self.tls_context = self.create_tls_context() if self.tls else None
        (self.reader, self.writer) = await asyncio.wait_for(
            asyncio.open_connection(
                host=self.hostname,
                port=self.port,
                local_addr=self.source_address,
                ssl=self.tls_context,
                server_hostname=self.server_hostname if self.tls else None,
            ),
            timeout=self.CONNECT_TIMEOUT,
        )


class FIDO(pydle.Client):
    """
    The bot. Any loss of the IRC session ends run_session() with EXIT_SESSION_LOST; there is no
    in-process reconnect, the container's restart policy starts a fresh process.
    """
    RECONNECT_ON_ERROR = False
    operchannel: str = None

    def __init__(self, *args, **kwargs):
        self.recent_greeting = {}  # normalized nick -> time.monotonic() of the #NewRats greeting
        self.oper_cache = {}  # normalized nick -> (expiry, is IRC operator); see modules.access
        self.oper_cache_generation = 0  # bumped by every nick change or quit
        self._join_waiters = {}  # normalized channel -> future resolved by FIDO's own JOIN echo
        self.opered = False
        self.snomask = None
        self.shutdown_requested = False
        self._exit_code = None
        self._exit_not_before = 0.0
        self._last_line = 0.0
        self._startup_timer = None
        self._read_loop_done = None
        self._read_task = None
        self._shutdown_task = None
        super().__init__(*args, **kwargs)

    # Session lifecycle

    async def run_session(self) -> int:
        """Connect, run until the session ends, and return the process exit code."""
        loop = asyncio.get_running_loop()
        self._exit_code = loop.create_future()
        self._read_loop_done = asyncio.Event()
        self._last_line = loop.time()
        self._startup_timer = loop.call_later(IRC.startupDeadline, self._startup_deadline_passed)
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.request_shutdown)
        watchdog = asyncio.create_task(self._watch_silence())
        connecting = asyncio.create_task(self._connect_session())
        try:
            return await self._exit_code
        finally:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)
            self._startup_timer.cancel()
            if self.connected:
                await self.disconnect(expected=True)
            tasks = [task for task in (watchdog, connecting, self._read_task) if task is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _connect_session(self):
        try:
            await self.connect(IRC.server, IRC.port, tls=IRC.useSsl, tls_verify=IRC.tlsVerify,
                               tls_server_name=IRC.tlsServerName)
        except Exception as error:
            self.end_session(EXIT_SESSION_LOST, f"connect to {IRC.server}:{IRC.port} failed: {error!r}")

    def end_session(self, code: int, reason: str):
        """
        Resolve the session's exit code; only the first call counts. A failure waits until any OPER
        back-off has passed, a shutdown (EXIT_OK) does not wait.
        """
        exit_code = self._exit_code
        if exit_code is None or exit_code.done():
            return
        loop = exit_code.get_loop()
        wait = self._exit_not_before - loop.time()
        if code != EXIT_OK and wait > 0:
            loop.call_later(wait, self.end_session, code, reason)
            return
        if code == EXIT_OK:
            log.info(f"Session ended: {reason}")
        else:
            log.error(f"Session lost, exiting with {code}: {reason}")
        exit_code.set_result(code)

    def _startup_deadline_passed(self):
        if not self.opered:
            self.end_session(EXIT_SESSION_LOST, f"not opered within {IRC.startupDeadline} s of connecting")

    async def _watch_silence(self):
        loop = asyncio.get_running_loop()
        interval = min(WATCHDOG_INTERVAL, IRC.silenceLimit / 2)
        while True:
            await asyncio.sleep(interval)
            silent = loop.time() - self._last_line
            if silent >= IRC.silenceLimit:
                self.end_session(EXIT_SESSION_LOST, f"no line received for {silent:.0f} s")
                return

    def request_shutdown(self):
        """SIGTERM and SIGINT: send QUIT, wait up to SHUTDOWN_GRACE seconds for the close, then exit 0."""
        if self.shutdown_requested:
            return
        self.shutdown_requested = True
        log.info("Shutdown requested")
        self._shutdown_task = asyncio.get_running_loop().create_task(self._shutdown())

    async def _shutdown(self):
        try:
            async with asyncio.timeout(SHUTDOWN_GRACE):
                if self.connected:
                    await self.rawmsg('QUIT', QUIT_MESSAGE)
                    await self._read_loop_done.wait()
        except (TimeoutError, OSError) as error:
            log.warning(f"No clean close after QUIT: {error!r}")
        self.end_session(EXIT_OK, "shutdown requested")

    # pydle overrides for the session

    async def _connect(self, hostname, port, reconnect=False, password=None,
                       encoding=pydle.protocol.DEFAULT_ENCODING, channels=None,
                       tls=False, tls_verify=False, tls_server_name=None, source_address=None):
        """TLSSupport._connect with a separate TLS server name, which pydle cannot pass on."""
        self.password = password
        self._autojoin_channels = channels or []
        self.connection = ServerNameConnection(
            hostname,
            port,
            source_address=source_address,
            tls=tls,
            tls_verify=tls_verify,
            tls_certificate_file=self.tls_client_cert,
            tls_certificate_keyfile=self.tls_client_cert_key,
            tls_certificate_password=self.tls_client_cert_password,
            server_hostname=tls_server_name,
        )
        self.encoding = encoding
        await self.connection.connect()

    async def handle_forever(self):
        """pydle's read loop. However it ends, the session ends, unless a shutdown was requested."""
        self._read_task = asyncio.current_task()
        try:
            await super().handle_forever()
        except Exception as error:
            log.error(f"Read loop failed: {error!r}")
        finally:
            if self._read_loop_done is not None:
                self._read_loop_done.set()
            if not self.shutdown_requested:
                self.end_session(EXIT_SESSION_LOST, "read loop ended")

    async def on_data(self, data):
        self._last_line = asyncio.get_running_loop().time()
        await super().on_data(data)

    async def on_disconnect(self, expected):
        await super().on_disconnect(expected)
        if not self.shutdown_requested:
            self.end_session(EXIT_SESSION_LOST, "disconnected" if expected else "disconnected unexpectedly")

    async def on_raw_error(self, message):
        if self.shutdown_requested:
            await self.disconnect(expected=True)
            return
        await super().on_raw_error(message)

    async def on_raw_001(self, message):
        await super().on_raw_001(message)
        if not self.is_same_nick(self.nickname, IRC.nickname):
            self.end_session(EXIT_SESSION_LOST, f"registered as {self.nickname}, not {IRC.nickname}")

    async def on_raw_008(self, message):
        """RPL_SNOMASK."""
        await super().on_raw_008(message)
        self.snomask = message.params[1] if len(message.params) > 1 else ''
        if self.opered:
            self._report_snomask()

    async def on_raw_381(self, message):
        """RPL_YOUREOPER."""
        self.opered = True
        if self._startup_timer is not None:
            self._startup_timer.cancel()
        if self.snomask is None:
            log.info("opered, snomask not reported yet")
            return
        self._report_snomask()

    async def on_raw_464(self, message):
        """ERR_PASSWDMISMATCH."""
        self._oper_failed("464 password mismatch")

    async def on_raw_491(self, message):
        """ERR_NOOPERHOST."""
        self._oper_failed("491 no matching oper block")

    def _report_snomask(self):
        log.info(f"opered, snomask {self.snomask}")
        if IRC.expectSnomask and self.snomask != IRC.expectSnomask:
            log.warning(f"snomask {self.snomask} differs from the expected {IRC.expectSnomask}")

    def _oper_failed(self, reason: str):
        backoff = OPER_FAIL_BACKOFF
        log.error(f"OPER failed ({reason}), exiting in {backoff} s")
        self._exit_not_before = asyncio.get_running_loop().time() + backoff
        self.end_session(EXIT_SESSION_LOST, f"OPER failed: {reason}")

    async def _send_oper(self):
        """Write OPER straight to the connection: pydle's _send logs every line it sends at DEBUG."""
        line = f"OPER {IRC.operline} {IRC.operlinePassword}\r\n"  # raw bytes, so the CRLF is required
        await self.connection.send(line.encode(self.encoding))
        log.info(f"OPER sent for {IRC.operline}")

    # IRC events

    async def on_connect(self):
        await super().on_connect()
        log.info("Connected!")
        await self._send_oper()
        channels = configmanager.get_config(module='channels', key='join')
        log.info(f"Joining {', '.join(channels) or 'no channels'}")
        # Join remembered channels
        for channel in channels:
            await self.join(channel)
        # TODO: Seed session cache by reading /who output on join?
        with session_scope() as session:
            monitored = [mon.nickname for mon in session.query(monitor.Monitor).all()]
        for nickname in monitored:
            await self.monitor(nickname)

    async def on_join(self, channel, user):
        await super().on_join(channel, user)
        if self.is_same_nick(user, self.nickname):
            waiter = self._join_waiters.get(self.normalize(channel))
            if waiter is not None and not waiter.done():
                waiter.set_result(True)
            # The ban list (367 lines) lets !unmute find the exact mute masks.
            await self.rawmsg('MODE', channel, 'b')
            return
        await induction.on_join(self, channel, user)
        # TODO: Maybe session cache here instead?

    async def join_confirmed(self, channel: str, timeout: float) -> bool:
        """Send JOIN and wait up to timeout seconds for the server's echo of FIDO's own JOIN."""
        key = self.normalize(channel)
        waiter = asyncio.get_running_loop().create_future()
        self._join_waiters[key] = waiter
        try:
            await self.join(channel)
            await asyncio.wait_for(waiter, timeout)
            return True
        except TimeoutError:
            return False
        finally:
            if self._join_waiters.get(key) is waiter:
                del self._join_waiters[key]

    async def on_raw_367(self, message):
        """RPL_BANLIST: one ban list entry, kept in the list pydle updates from +b/-b changes."""
        channel, mask = message.params[1], message.params[2]
        if not self.in_channel(channel):
            return
        bans = self.channels[channel]['modes'].setdefault('b', [])
        if mask not in bans:
            bans.append(mask)

    async def on_raw_368(self, message):
        """RPL_ENDOFBANLIST: the 367 lines before it already filled the list."""

    async def on_nick_change(self, old, new):
        await super().on_nick_change(old, new)
        access.forget_oper(self, old)
        access.forget_oper(self, new)

    async def on_quit(self, user, message=None):
        await super().on_quit(user, message)
        access.forget_oper(self, user)

    async def on_channel_message(self, target, nick, message):
        await super().on_channel_message(target, nick, message)
        if nick == self.nickname:
            return
        await channelprotectionhandler.handle_message(self, target, nick, message)
        await commandHandler.on_channel_message(self, target, nick, message)

    async def on_ctcp(self, by, target, what, contents):
        await super().on_ctcp(by, target, what, contents)
        if by == self.nickname:
            return
        if what == 'ACTION' and self.is_channel(target):
            await channelprotectionhandler.handle_message(self, target, by, contents)

    async def on_private_message(self, target, nick, message):
        await super().on_private_message(target, nick, message)
        await commandHandler.on_private_message(self, nick, message)

    async def on_notice(self, target, by, message):
        """
        Only server notices addressed to FIDO reach the notice handlers. pydle passes the bare server
        name as `by` for a server prefix and the bare nick for a user; nicks cannot contain a dot.
        """
        await super().on_notice(target, by, message)
        if not (by and '.' in by and self.is_same_nick(target, self.nickname)):
            return
        await noticehandler.handle_notice(self, message)

    async def on_user_online(self, nickname):
        await super().on_user_online(nickname)
        log.debug(f"Monitored user {nickname} is online.")
        await self.message(self.get_ratops_channel(), f"Monitored user {nickname} is online!")

    async def on_user_offline(self, nickname):
        await super().on_user_offline(nickname)
        log.debug(f"Monitored user {nickname} is now offline.")
        await self.message(self.get_ratops_channel(), f"Monitored user {nickname} is now offline.")

    @staticmethod
    def colour_red(message: str):
        return f"\u000304{message}\u000f"

    @staticmethod
    def colour_yellow(message: str):
        return f"\u000308{message}\u000f"

    @staticmethod
    def colour_green(message: str):
        return f"\u000303{message}\u000f"

    def get_oper_channel(self):
        if self.operchannel is None:
            self.operchannel = configmanager.get_value('channels', 'operchannel')
        return self.operchannel

    @staticmethod
    def get_ratops_channel():
        return configmanager.get_value('channels', 'ratops')


def config_problems() -> list:
    """Settings main() refuses to start with."""
    problems = []
    if not IRC.operline:
        problems.append("FIDO_OPER_NAME is not set")
    if not IRC.operlinePassword:
        problems.append("FIDO_OPER_PASSWORD is not set")
    if Logging.level not in logging.getLevelNamesMapping():
        problems.append(f"FIDO_LOG_LEVEL {Logging.level!r} is not a logging level name")
    if IRC.startupDeadline <= 0:
        problems.append("FIDO_STARTUP_DEADLINE must be above 0")
    if IRC.silenceLimit <= 0:
        problems.append("FIDO_SILENCE_LIMIT must be above 0")
    return problems


async def main() -> int:
    """Run one IRC session; the return value is the process exit code."""
    logging.basicConfig(stream=sys.stdout, level=logging.getLevelNamesMapping().get(Logging.level, logging.INFO))
    problems = config_problems()
    if problems:
        for problem in problems:
            log.critical(f"Configuration error: {problem}")
        return EXIT_CONFIG
    client = FIDO(IRC.nickname)
    return await client.run_session()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))

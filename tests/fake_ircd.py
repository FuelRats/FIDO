"""
A scripted IRC server for tests. It serves one client at a time on 127.0.0.1 and an ephemeral
port, plaintext or TLS, as irc.example.test, and answers just enough of UnrealIRCd's protocol
for FIDO to register and oper. Synthetic data only.

    ircd = FakeIRCd()                 # or FakeIRCd(ssl=server_context)
    ircd.oper_reply = '464'           # behaviour knobs, set before the client connects
    port = await ircd.start()
    ...
    await ircd.wait_for_line('OPER ')
    await ircd.close_client(reset=True)
    await ircd.stop()
"""
import asyncio
import socket
import struct

SERVER_NAME = 'irc.example.test'
DEFAULT_SNOMASK = '+bcdfkoqsBCOS'
OPER_OK = 'ok'
WAIT_TIMEOUT = 5  # seconds
POLL_INTERVAL = 0.01  # seconds


class FakeIRCd:
    def __init__(self, *, ssl=None, server_name=SERVER_NAME):
        self.ssl = ssl
        self.server_name = server_name
        # Behaviour
        self.register = True  # answer NICK and USER with 001-005 and the MOTD; False: read and stay silent
        self.taken_nicks = set()  # NICK with one of these gets 433
        self.oper_reply = OPER_OK  # OPER_OK (008 then 381), '464', '491', or None for no answer
        self.snomask = DEFAULT_SNOMASK
        # Observations
        self.received = []  # every line from the client, line ending stripped
        self.connections = 0
        self.nick = None
        self._server = None
        self._writer = None
        self._user_seen = False
        self._registered = False

    # Control

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, '127.0.0.1', 0, ssl=self.ssl)
        return self.port

    @property
    def port(self) -> int:
        return self._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._writer is not None:
            self._writer.transport.abort()
        self._server.close()
        await self._server.wait_closed()

    async def send(self, line: str):
        """Send one line to the connected client."""
        self._writer.write((line + '\r\n').encode('utf-8'))
        await self._writer.drain()

    async def close_client(self, reset=False):
        """Close the client's connection; reset=True sends a TCP RST (SO_LINGER 1, 0) instead of FIN."""
        writer = self._writer
        if reset:
            sock = writer.get_extra_info('socket')
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            writer.transport.abort()
            return
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass

    async def wait_for_line(self, prefix: str, timeout=WAIT_TIMEOUT) -> str:
        """The first received line starting with prefix, waiting for it if needed."""
        async with asyncio.timeout(timeout):
            while True:
                for line in self.received:
                    if line.startswith(prefix):
                        return line
                await asyncio.sleep(POLL_INTERVAL)

    # Protocol

    async def _handle(self, reader, writer):
        self.connections += 1
        self._writer = writer
        self.nick = None
        self._user_seen = False
        self._registered = False
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                self.received.append(line)
                await self._respond(line)
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    async def _numeric(self, numeric: str, text: str):
        await self.send(f":{self.server_name} {numeric} {self.nick or '*'} {text}")

    async def _respond(self, line: str):
        command, _, rest = line.partition(' ')
        command = command.upper()
        if command == 'NICK' and self.register:
            await self._on_nick(rest.split(' ')[0].lstrip(':'))
        elif command == 'USER' and self.register:
            self._user_seen = True
            await self._maybe_register()
        elif command == 'OPER':
            await self._on_oper()
        elif command == 'PING':
            await self.send(f":{self.server_name} PONG {self.server_name} :{rest.lstrip(':')}")
        elif command == 'WHOIS':
            await self._on_whois(rest.split(' ')[-1].lstrip(':'))
        elif command == 'JOIN' and self._registered:
            await self.send(f":{self.nick}!{self.nick.lower()}@{self.server_name} JOIN :{rest.split(' ')[0]}")
        elif command == 'QUIT':
            await self.send(f"ERROR :Closing Link: {self.nick}[127.0.0.1] (Quit: {rest.lstrip(':')})")
            self._writer.close()

    async def _on_nick(self, wanted: str):
        if not self._registered and wanted in self.taken_nicks:
            await self.send(f":{self.server_name} 433 {self.nick or '*'} {wanted} :Nickname is already in use.")
            return
        self.nick = wanted
        await self._maybe_register()

    async def _maybe_register(self):
        if self._registered or not self.nick or not self._user_seen:
            return
        self._registered = True
        server = self.server_name
        await self._numeric('001', f":Welcome to the Example IRC Network {self.nick}!{self.nick.lower()}@{server}")
        await self._numeric('002', f":Your host is {server}, running version fakeircd-1")
        await self._numeric('003', ":This server was created today")
        await self._numeric('004', f"{server} fakeircd-1 iowrsxzBDGHIRSTWZ beIqaohvlkL")
        await self._numeric('005', "PREFIX=(qaohv)~&@%+ CHANMODES=beI,fkL,lFH,cdimnprstzCDGKMNOPQRSTVZ "
                                   "CASEMAPPING=ascii MONITOR=128 WHOX NETWORK=Example :are supported by this server")
        await self._numeric('375', f":- {server} Message of the Day -")
        await self._numeric('372', ":- synthetic test server")
        await self._numeric('376', ":End of /MOTD command.")

    async def _on_whois(self, target: str):
        """Only the client itself exists; pydle waits for 318 or 401 (it asks about '<unregistered>' at 001)."""
        if target == self.nick:
            await self._numeric('311', f"{target} {target.lower()} {self.server_name} * :{target}")
        else:
            await self._numeric('401', f"{target} :No such nick/channel")
        await self._numeric('318', f"{target} :End of /WHOIS list.")

    async def _on_oper(self):
        if self.oper_reply == OPER_OK:
            await self._numeric('008', f"{self.snomask} :Server notice mask")
            await self._numeric('381', ":You are now an IRC Operator")
        elif self.oper_reply == '464':
            await self._numeric('464', ":Password Incorrect")
        elif self.oper_reply == '491':
            await self._numeric('491', ":No O-lines for your host")

"""
A scripted IRC server for tests. It serves one client at a time on 127.0.0.1 and an ephemeral
port, plaintext or TLS, as irc.example.test, and answers just enough of UnrealIRCd's protocol
for FIDO to register and oper: CAP LS 302 split over two lines (registration waits for CAP END,
as on UnrealIRCd), CAP REQ, and SASL PLAIN. Synthetic data only.

    ircd = FakeIRCd()                 # or FakeIRCd(ssl=server_context)
    ircd.oper_reply = '464'           # behaviour knobs, set before the client connects
    ircd.cap_ls = CAP_LS_WITH_SASL
    ircd.sasl_accounts = {'FIDO[BOT]': password}
    port = await ircd.start()
    ...
    await ircd.wait_for_line('OPER ')
    await ircd.cap_new(SASL_TOKEN)    # services link: CAP NEW sasl
    await ircd.close_client(reset=True)
    await ircd.stop()
"""
import asyncio
import base64
import binascii
import socket
import struct

SERVER_NAME = 'irc.example.test'
DEFAULT_SNOMASK = '+bcdfkoqsBCOS'
OPER_OK = 'ok'
WAIT_TIMEOUT = 5  # seconds
POLL_INTERVAL = 0.01  # seconds

SASL_MECHANISMS = 'ANONYMOUS,EXTERNAL,PLAIN'
SASL_TOKEN = f'sasl={SASL_MECHANISMS}'
SASL_CHUNK = 400  # base64 bytes per AUTHENTICATE line
# UnrealIRCd 6.2.6 splits its CAP LS 302 reply over two lines; sasl is on the first, and is
# missing while services are not linked.
_CAP_LS_FIRST = ('account-notify away-notify cap-notify chghost echo-message extended-join invite-notify '
                 'message-tags multi-prefix {sasl}server-time setname tls userhost-in-names')
_CAP_LS_LAST = 'draft/multiline=max-bytes=5250,max-lines=15 unrealircd.org/json-log'
CAP_LS_WITHOUT_SASL = (_CAP_LS_FIRST.format(sasl=''), _CAP_LS_LAST)
CAP_LS_WITH_SASL = (_CAP_LS_FIRST.format(sasl=SASL_TOKEN + ' '), _CAP_LS_LAST)

CLIENT = 'client'  # transcript direction: a line the client sent
SERVER = 'server'  # transcript direction: a line the server sent


def capability_name(token: str) -> str:
    return token.lstrip('-~=').split('=', 1)[0].lower()


class FakeIRCd:
    def __init__(self, *, ssl=None, server_name=SERVER_NAME):
        self.ssl = ssl
        self.server_name = server_name
        # Behaviour
        self.register = True  # answer NICK and USER with 001-005 and the MOTD; False: read and stay silent
        self.taken_nicks = set()  # NICK with one of these gets 433
        self.oper_reply = OPER_OK  # OPER_OK (008 then 381), '464', '491', or None for no answer
        self.snomask = DEFAULT_SNOMASK
        self.cap_ls = CAP_LS_WITHOUT_SASL  # lines of the CAP LS reply; () leaves CAP LS unanswered
        self.sasl_accounts = {}  # account -> password that SASL PLAIN accepts; anything else gets 904
        self.sasl_answers = True  # False: AUTHENTICATE PLAIN gets no reply, as when services do not answer
        # Observations
        self.received = []  # every line from the client, line ending stripped
        self.transcript = []  # (CLIENT or SERVER, line) in the order sent
        self.sasl_responses = []  # each complete SASL PLAIN response, base64-decoded
        self.connections = 0
        self.nick = None
        self._server = None
        self._writer = None
        self._user_seen = False
        self._registered = False
        self._cap_open = False
        self._offered = {}
        self._sasl_buffer = None

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
        self.transcript.append((SERVER, line))
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

    async def cap_new(self, caps: str):
        """Announce capabilities, as UnrealIRCd does for sasl when services link."""
        for token in caps.split():
            self._offered[capability_name(token)] = token
        await self.send(f":{self.server_name} CAP {self.nick or '*'} NEW :{caps}")

    async def cap_del(self, caps: str):
        """Withdraw capabilities, as UnrealIRCd does for sasl when services quit."""
        for name in caps.split():
            self._offered.pop(capability_name(name), None)
        await self.send(f":{self.server_name} CAP {self.nick or '*'} DEL :{caps}")

    async def force_nick(self, new: str):
        """Rename the client, as services do with SVSNICK."""
        old = self.nick
        self.nick = new
        await self.send(f":{old}!{old.lower()}@{self.server_name} NICK :{new}")

    # Protocol

    async def _handle(self, reader, writer):
        self.connections += 1
        self._writer = writer
        self.nick = None
        self._user_seen = False
        self._registered = False
        self._cap_open = False
        self._offered = {}
        self._sasl_buffer = None
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                self.received.append(line)
                self.transcript.append((CLIENT, line))
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
        if command == 'CAP' and self.register:
            await self._on_cap(rest)
        elif command == 'AUTHENTICATE' and self.register:
            await self._on_authenticate(rest.lstrip(':'))
        elif command == 'NICK' and self.register:
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

    async def _on_cap(self, rest: str):
        subcommand, _, args = rest.partition(' ')
        subcommand = subcommand.upper()
        target = self.nick or '*'
        if subcommand == 'LS' and self.cap_ls:
            if not self._registered:
                self._cap_open = True
            self._offered = {capability_name(token): token for line in self.cap_ls for token in line.split()}
            for line in self.cap_ls[:-1]:
                await self.send(f":{self.server_name} CAP {target} LS * :{line}")
            await self.send(f":{self.server_name} CAP {target} LS :{self.cap_ls[-1]}")
        elif subcommand == 'REQ':
            wanted = args.lstrip(':').split()
            verb = 'ACK' if all(capability_name(token) in self._offered for token in wanted) else 'NAK'
            await self.send(f":{self.server_name} CAP {target} {verb} :{' '.join(wanted)}")
        elif subcommand == 'END':
            self._cap_open = False
            await self._maybe_register()

    async def _on_authenticate(self, data: str):
        if data == '*':
            self._sasl_buffer = None
            await self._numeric('906', ':SASL authentication aborted')
            return
        if self._sasl_buffer is None:
            if not self.sasl_answers:
                return
            if data.upper() != 'PLAIN':
                await self._numeric('904', ':SASL authentication failed')
                return
            self._sasl_buffer = ''
            await self.send('AUTHENTICATE +')
            return
        if data != '+':
            self._sasl_buffer += data
        if data == '+' or len(data) < SASL_CHUNK:
            encoded, self._sasl_buffer = self._sasl_buffer, None
            await self._check_plain(encoded)

    async def _check_plain(self, encoded: str):
        try:
            response = base64.b64decode(encoded, validate=True)
        except binascii.Error:
            response = b''
        self.sasl_responses.append(response)
        parts = response.split(b'\0')
        if len(parts) == 3:
            authzid, authcid, password = (part.decode('utf-8', 'replace') for part in parts)
            if authzid in ('', authcid) and self.sasl_accounts.get(authcid) == password:
                nick = self.nick or '*'
                await self._numeric('900', f"{nick}!{nick.lower()}@{self.server_name} {authcid} "
                                           f":You are now logged in as {authcid}")
                await self._numeric('903', ':SASL authentication successful')
                return
        await self._numeric('904', ':SASL authentication failed')

    async def _on_nick(self, wanted: str):
        if not self._registered and wanted in self.taken_nicks:
            await self.send(f":{self.server_name} 433 {self.nick or '*'} {wanted} :Nickname is already in use.")
            return
        self.nick = wanted
        await self._maybe_register()

    async def _maybe_register(self):
        if self._registered or self._cap_open or not self.nick or not self._user_seen:
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

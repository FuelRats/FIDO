"""
A small IRC client for the test bed (tests/testbed/run.sh). It connects over TLS, verified against
the test bed's CA (SSL_CERT_FILE), registers, optionally opers, sends raw lines, stays a while
and quits. Standard library only. Examples:

    python -I ircclient.py --server leaf.irc.example.test --nick Jameson --stay 3
    python -I ircclient.py --server hub.irc.example.test --nick TestOper --oper testop \\
        --send 'KILL FIDO[BOT] :test bed'

The oper password is read from TESTBED_TESTOP_PASSWORD and never printed.
"""
import argparse
import os
import socket
import ssl
import sys
import time

PORT = 6697
TIMEOUT = 30  # seconds for the connection and for each awaited reply
OPER_REFUSED = {'464', '491'}


class Session:
    def __init__(self, sock):
        self.sock = sock
        self.buffer = b''

    def send(self, line: str):
        self.sock.sendall((line + '\r\n').encode('utf-8'))

    def read_line(self, deadline: float):
        """The next line from the server, answering PING on the way; None once deadline passes."""
        while b'\r\n' not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self.sock.settimeout(remaining)
            try:
                data = self.sock.recv(4096)
            except TimeoutError:
                return None
            if not data:
                raise ConnectionError('the server closed the connection')
            self.buffer += data
        raw, self.buffer = self.buffer.split(b'\r\n', 1)
        line = raw.decode('utf-8', 'replace')
        if line.startswith('PING '):
            self.send('PONG ' + line[5:])
        return line

    def wait_for(self, numeric: str, refused=frozenset()):
        """Read until the server sends numeric; fail on a numeric in refused or after TIMEOUT."""
        deadline = time.monotonic() + TIMEOUT
        while True:
            line = self.read_line(deadline)
            if line is None:
                raise TimeoutError(f'no {numeric} within {TIMEOUT} s')
            parts = line.split(' ')
            code = parts[1] if line.startswith(':') and len(parts) > 1 else None
            if code == numeric:
                return
            if code in refused:
                raise PermissionError(f'the server refused with {code}')

    def stay(self, seconds: float):
        deadline = time.monotonic() + seconds
        while self.read_line(deadline) is not None:
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Test bed IRC client.')
    parser.add_argument('--server', required=True)
    parser.add_argument('--nick', required=True)
    parser.add_argument('--oper', help='oper block name; the password comes from TESTBED_TESTOP_PASSWORD')
    parser.add_argument('--send', action='append', default=[], help='raw line to send once ready (repeatable)')
    parser.add_argument('--stay', type=float, default=1.0, help='seconds to stay connected before QUIT')
    args = parser.parse_args(argv)

    context = ssl.create_default_context()
    with socket.create_connection((args.server, PORT), timeout=TIMEOUT) as raw, \
            context.wrap_socket(raw, server_hostname=args.server) as sock:
        session = Session(sock)
        session.send(f'NICK {args.nick}')
        session.send(f'USER {args.nick.lower()} 0 * :FIDO test bed client')
        session.wait_for('001')
        print(f'{args.nick} registered on {args.server}')
        if args.oper:
            session.send(f"OPER {args.oper} {os.environ['TESTBED_TESTOP_PASSWORD']}")
            session.wait_for('381', refused=OPER_REFUSED)
            print(f'{args.nick} opered as {args.oper}')
        for line in args.send:
            session.send(line)
            print(f'{args.nick} sent {line.split(" ", 1)[0]}')
        session.stay(args.stay)
        session.send('QUIT :done')
    return 0


if __name__ == '__main__':
    sys.exit(main())

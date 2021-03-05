import logging


class IRC:
    server = '127.0.0.1'  # Set this to your IRC server
    port = 6697  # IRC server port
    useSsl = True  # Set to true if connecting with SSL
    nickname = 'FIDO[BOT]'  # Nickname bot will use
    commandPrefix = '!'  # Prefix for all FIDO commands
    operline = 'fido-py'  # What operline should FIDO attempt to claim?
    operlinePassword = 'agoodpassword'  # Password for the operline


class Logging:
    filename = 'FIDO.log'  # Filename main log is written to
    level = logging.DEBUG  # What loglevel to write to log


class SQLAlchemy:
    url = 'sqlite:///FIDO.sqlite'  # SQLAlchemy URL for database connection


class SessionHandler:
    retention_time = 90  # How many days should the session handler retain sessions?


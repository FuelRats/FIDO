import logging


class IRC:
    server = '192.168.1.21'
    port = 6697
    useSsl = True
    nickname = 'FIDO-dev'
    commandPrefix = '!'
    operline = 'fido_local'
    operlinePassword = 'squeak'


class Logging:
    filename = 'FIDO.log'
    level = logging.DEBUG


class SQLAlchemy:
    url = 'sqlite:///FIDO.sqlite'


class SessionHandler:
    retention_time = 90

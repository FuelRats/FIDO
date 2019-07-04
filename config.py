import logging

class IRC:
    channel = '#adadev'
    server = 'irc.fuelrats.com'
    port = 6697
    useSsl = True
    nickname = 'FIDO-dev'
    commandPrefix = '!'


class Logging:
    filename = 'FIDO.log'
    level = logging.DEBUG

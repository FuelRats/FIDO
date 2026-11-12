"""
FIDO settings, read from the environment at import.

An unset or empty variable takes the default shown. Booleans accept
1/true/yes/on and 0/false/no/off (any case); anything else raises ValueError.
Required values (the oper name and password) and the SASL pair (both or
neither) are checked by fido.main(), not here, so the code imports without
secrets.
"""
import os

_TRUE = {'1', 'true', 'yes', 'on'}
_FALSE = {'0', 'false', 'no', 'off'}


def env_str(name: str, default: str = '') -> str:
    """Return the variable's value, or default when it is unset or empty."""
    return os.environ.get(name) or default


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if not raw:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{name} must be one of 1/true/yes/on or 0/false/no/off, got {raw!r}")


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


class IRC:
    server = env_str('FIDO_IRC_SERVER', '127.0.0.1')
    port = env_int('FIDO_IRC_PORT', 6697)
    useSsl = env_bool('FIDO_IRC_TLS', True)
    tlsVerify = env_bool('FIDO_TLS_VERIFY', False)
    tlsServerName = env_str('FIDO_TLS_SERVERNAME')  # certificate name to verify and send as SNI; empty uses server
    nickname = env_str('FIDO_NICK', 'FIDO[BOT]')
    commandPrefix = '!'
    operline = env_str('FIDO_OPER_NAME')
    operlinePassword = env_str('FIDO_OPER_PASSWORD')
    saslUsername = env_str('FIDO_SASL_USERNAME')  # services account; empty with the password: no SASL login
    saslPassword = env_str('FIDO_SASL_PASSWORD')
    expectSnomask = env_str('FIDO_EXPECT_SNOMASK')  # empty: no check
    startupDeadline = env_int('FIDO_STARTUP_DEADLINE', 90)  # seconds from connect start to 381
    silenceLimit = env_int('FIDO_SILENCE_LIMIT', 360)  # seconds without a received line


class Logging:
    level = env_str('FIDO_LOG_LEVEL', 'INFO').strip().upper()


class SQLAlchemy:
    url = env_str('FIDO_DB_URL', 'sqlite:///FIDO.sqlite')


class SessionHandler:
    retention_time = env_int('FIDO_SESSION_RETENTION_DAYS', 90)  # days of sessions kept

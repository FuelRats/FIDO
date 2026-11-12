import logging

from models import config, session_scope

log = logging.getLogger(__name__)

DEFAULT_KICK_REASON = ('You must not attempt to disrupt the IRC servers, services or the servers they run '
                       'on, including but not limited to DDoS attacks, attempts to gain privileges, '
                       'flooding or otherwise interfering with the service(s).')

# Values used when a row is missing; scripts/initializedb.py seeds the same values.
DEFAULTS = {
    ('channelprotection', 'droneinterval'): '10',
    ('channelprotection', 'maxdrones'): '3',
    ('channelprotection', 'maxhighlightcount'): '5',
    ('channelprotection', 'maxmessages'): '4',
    ('channelprotection', 'messageinterval'): '6',
    ('channelprotection', 'mutetime'): '4',
    ('channelprotection', 'reason'): DEFAULT_KICK_REASON,
    ('channels', 'operchannel'): '#opers',
    ('channels', 'puppet_permission'): '#ratchat',
}

FLAG_ON = 'on'
FLAG_OFF = 'off'

# Runtime gates as (module, key), read with get_flag on every use; a missing row means on.
GATE_OPERS_REPORTS = ('notices', 'opers_reports')
GATE_SMS = ('notices', 'sms')
GATE_RATCHAT_LINK_WARNINGS = ('notices', 'ratchat_link_warnings')
GATE_DEFAULT = True


def get_config(module, key):
    """
    Get a config parameter
    :param module: Config Module
    :param key: Key to fetch
    :return: A list of matching config variables
    """
    with session_scope() as session:
        return [result.value for result in session.query(config.Config).filter_by(module=module, key=key)]


def get_value(module, key):
    """
    Get a single-valued config parameter.
    :return: The first stored value, else the value in DEFAULTS, else None
    """
    values = get_config(module, key)
    if values:
        return values[0]
    return DEFAULTS.get((module, key))


def get_flag(module, key, default: bool) -> bool:
    """
    Read an on/off gate. Read on every use, so a change in the DB applies without a restart.
    :return: True for 'on', False for 'off' (any case), default when the row is missing or holds anything else
    """
    values = get_config(module, key)
    if not values:
        return default
    if len(values) > 1:
        log.warning(f"Config {module}/{key} has {len(values)} rows, using the first")
    value = values[0].strip().lower()
    if value == FLAG_ON:
        return True
    if value == FLAG_OFF:
        return False
    log.warning(f"Config {module}/{key} is neither '{FLAG_ON}' nor '{FLAG_OFF}', using the default")
    return default


def gate_open(gate) -> bool:
    """Whether a runtime gate (one of the GATE_ pairs) is on."""
    module, key = gate
    return get_flag(module, key, GATE_DEFAULT)


def set_config(module, key, value):
    """
    Replace every row for module/key with one row holding value.
    :return: The values that were replaced (empty if there were none)
    """
    with session_scope() as session:
        rows = session.query(config.Config).filter_by(module=module, key=key)
        old = [row.value for row in rows]
        rows.delete()
        session.add(config.Config(module=module, key=key, value=value))
    return old


def del_config(module, key):
    with session_scope() as session:
        session.query(config.Config).where(config.Config.module == module).\
            where(config.Config.key == key).delete()

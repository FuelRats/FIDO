"""
Read-only check of a FIDO database: runs every read query the modules use against FIDO_DB_URL and
prints counts and key names only, never a stored value. On SQLite every connection is switched to
PRAGMA query_only, so an accidental write fails instead of changing the file.

Run as: FIDO_DB_URL=sqlite:////data/FIDO.sqlite python -m tools.staging_check
"""
import sys

from sqlalchemy import create_engine, event, func

import models
from config import SQLAlchemy
from models import asn_blacklist, config, drones, ircsessions, messagecounter, monitor, session_scope
from modules import configmanager, sessiontracker, sms
from modules.channelprotections import droneprotection
from modules.networkprotection import asn_blacklist as asn_protection

# Every (module, key) the code reads, besides the sms/topic/<group> keys.
CONFIG_KEYS = sorted(set(configmanager.DEFAULTS) | set(configmanager.GATES) | {
    ('channelprotection', 'reason_highlight'),
    ('channelprotection', 'reason_flood'),
    ('channelprotection', 'reason_zalgo'),
    ('channels', 'join'),
    ('commandhandler', 'bothost'),
    droneprotection.LOCKDOWN_STATE,
})

# Synthetic lookups: a documentation address, nick and AS number.
PROBE_IP = '192.0.2.1'
PROBE_NICK = 'Jameson'
PROBE_ASN = 'AS64496'


def read_only_engine(url: str):
    engine = create_engine(url)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def query_only(dbapi_connection, _record):
            dbapi_connection.execute('PRAGMA query_only = ON')
    return engine


def rows(count: int) -> str:
    return f"{count} row" if count == 1 else f"{count} rows"


def report(write):
    write("config keys read by the code:\n")
    for module, key in CONFIG_KEYS:
        write(f"  {module}/{key}: {rows(len(configmanager.get_config(module, key)))}\n")
    with session_scope() as session:
        topic_keys = sorted(row.key for row in session.query(config.Config).filter(
            config.Config.module == sms.TOPIC_MODULE, config.Config.key.startswith(sms.TOPIC_KEY_PREFIX)))
    names = ', '.join(f'{sms.TOPIC_MODULE}/{key}' for key in topic_keys)
    write(f"  {sms.TOPIC_MODULE}/{sms.TOPIC_KEY_PREFIX}*: {len(topic_keys)} key{'' if len(topic_keys) == 1 else 's'}"
          f"{': ' + names if names else ''}\n")

    with session_scope() as session:
        sessions = len(sessiontracker.previous_sessions(session, PROBE_NICK, PROBE_IP))
        total_sessions = session.query(func.count(ircsessions.IRCSessions.id)).scalar()
        monitored = session.query(monitor.Monitor).all()
        monitor_hits = session.query(monitor.Monitor).filter(monitor.Monitor.nickname == PROBE_NICK).count()
        banned_rows = session.query(func.count(asn_blacklist.ASNBlacklist.id)).scalar()
        banned_asns = session.query(func.count(asn_blacklist.ASNBlacklist.asn.distinct())).scalar()
        probe_asn_rows = session.query(asn_blacklist.ASNBlacklist).filter(
            asn_blacklist.ASNBlacklist.asn == PROBE_ASN).count()
        drone_rows = session.query(drones.Drones).count()
        probe_messages = session.query(messagecounter.Messagecounter).filter(
            messagecounter.Messagecounter.nickname == PROBE_NICK).count()
    write(f"session tracker: {rows(total_sessions)}, lookup of {PROBE_NICK} or {PROBE_IP}: {rows(sessions)}\n")
    write(f"monitor list: {rows(len(monitored))}, lookup of {PROBE_NICK}: {rows(monitor_hits)}\n")

    asn_protection.forget_prefixes()
    loaded = len(asn_protection.load_prefixes())
    banned = asn_protection.check_ban(PROBE_IP) is not None
    asn_protection.forget_prefixes()
    write(f"ASN bans: {rows(banned_rows)} for {banned_asns} ASNs, {loaded} prefixes loaded, "
          f"{banned_rows - loaded} unparsable; {PROBE_IP} banned: {'yes' if banned else 'no'}; "
          f"lookup of {PROBE_ASN}: {rows(probe_asn_rows)}\n")
    write(f"drones: {rows(drone_rows)}; message counter lookup of {PROBE_NICK}: {rows(probe_messages)}\n")


def main(url: str = None, write=sys.stdout.write) -> int:
    engine = read_only_engine(url or SQLAlchemy.url)
    previous = models.engine
    models.use_engine(engine)
    try:
        report(write)
    finally:
        models.use_engine(previous)
        engine.dispose()
    write("staging check done, nothing written\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())

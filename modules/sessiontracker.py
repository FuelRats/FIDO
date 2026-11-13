import logging
import time

from sqlalchemy import or_

import datetime
import fido
import ipaddress
from config import SessionHandler
from models import ircsessions, monitor, session_scope

log = logging.getLogger(__name__)

PURGE_INTERVAL = 3600  # seconds between two purges of sessions past their retention time
CLIENT_PREFIXLEN = {4: 24, 6: 56}  # the network stored with each session

_next_purge = 0.0  # time.monotonic() at which the next purge is due; 0 means at the next session


def reset_purge_clock():
    """Make the next session run the purge (tests use it to isolate the hourly clock)."""
    global _next_purge
    _next_purge = 0.0


def previous_sessions(session, nickname, hostmask) -> list:
    """Stored sessions with the same nick or the same address, oldest first."""
    return session.query(ircsessions.IRCSessions) \
        .filter(or_(ircsessions.IRCSessions.nickname == nickname, ircsessions.IRCSessions.hostmask == hostmask)) \
        .order_by(ircsessions.IRCSessions.timestamp, ircsessions.IRCSessions.id) \
        .all()


def is_clone(nickname, hostmask, withdate=False):
    """
    Checks whether a nickname is considered a clone by the bot, and stores the session.
    :param withdate: Whether to return a tuple containing both matches and the last timestamp of connection
    :param hostmask: Hostmask of user
    :param nickname: Nickname of user
    :return: A list of the other nicknames seen from the same address, or None.
    """
    with session_scope() as session:
        clones, lasttime = _is_clone(session, nickname, hostmask)
    if withdate:
        return clones, lasttime
    return clones


def _is_clone(session, nickname, hostmask):
    """
    Every other nick seen from this address is a clone, whether or not this nick and address were seen
    together before. A new nick and address pair is stored; a known one gets its timestamp updated.
    :return: (clone nicks oldest first, newest timestamp among them), or (None, None) without clones
    """
    timestamp = datetime.datetime.now()
    try:
        ip = ipaddress.ip_address(hostmask)
    except ValueError:
        log.warning("Client connected without an IP address, session not tracked")
        return None, None
    network = ipaddress.ip_network(f"{ip}/{CLIENT_PREFIXLEN[ip.version]}", strict=False)
    clonenicks = []
    lasttime = None
    known_pair = None
    for row in previous_sessions(session, nickname, hostmask):
        if row.nickname == nickname and row.hostmask == hostmask:
            known_pair = row
        elif row.hostmask == hostmask:
            if row.nickname not in clonenicks:
                clonenicks.append(row.nickname)
            lasttime = row.timestamp
    if known_pair is not None:
        log.debug("Same nick from same IP, update timestamp.")
        known_pair.timestamp = timestamp
    else:
        session.add(ircsessions.IRCSessions(timestamp=timestamp, nickname=nickname, hostmask=hostmask,
                                            network=str(network)))
    purge_expired(session)
    if not clonenicks:
        return None, None
    log.debug(f"Clones: {clonenicks} Lasttime: {lasttime}")
    return clonenicks, lasttime


def purge_expired(session):
    """Delete sessions older than the retention time, at most once per PURGE_INTERVAL."""
    global _next_purge
    now = time.monotonic()
    if now < _next_purge:
        return
    _next_purge = now + PURGE_INTERVAL
    timeout = datetime.datetime.now() - datetime.timedelta(days=int(SessionHandler.retention_time))
    deleted = session.query(ircsessions.IRCSessions).filter(ircsessions.IRCSessions.timestamp < timeout).delete()
    if deleted:
        log.info(f"Deleted {deleted} old sessions.")


async def check_clone(bot: fido, nickname, hostmask):
    """
    Handle connection notifications and store sessions.
    :param bot: bot instance
    :param nickname: Nickname of user
    :param hostmask: Hostmask (Or rather just IP) of user
    :return: Nothing.
    """
    ratops = bot.get_ratops_channel()
    with session_scope() as session:
        sus_nick = session.query(monitor.Monitor).filter(monitor.Monitor.nickname == nickname).first()
    if sus_nick:
        log.debug("Sus nick found!")
        await bot.message(ratops, f"Monitored nick {nickname} has come online. "
                                  f"({sus_nick.msg or ''})")

    clones, lasttime = is_clone(nickname, hostmask, True)
    if clones is None:
        return
    with session_scope() as session:
        sus_nicks = {row.nickname for row in session.query(monitor.Monitor)}
    for clone in clones:
        if clone in sus_nicks:
            await bot.message(ratops, f"{bot.colour_red('MONITOR')} Nick {nickname} is a "
                                      f"clone of monitored nick {clone}!")
    await bot.message(bot.get_oper_channel(),
                      f"{bot.colour_red('CLONE')} {nickname} has connected from {hostmask}, "
                      f"previous nicknames: {', '.join(clones)} (Last connected {lasttime})")

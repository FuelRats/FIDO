import re
import socket

from sqlalchemy import or_

import datetime
import fido
import ipaddress
from config import SessionHandler
from models import SessionManager
from models import ircsessions, monitor


def is_clone(nickname, hostmask, withdate=False):
    """
    Checks whether a nickname is considered a clone by the bot.
    :param withdate: Whether to return a tuple containing both matches and the last timestamp of connection
    :param hostmask: Hostmask of user
    :param bot: bot instance
    :param nickname: Nickname of user
    :return: A list of nicknames previously used if the user is a clone, or None.
    """
    sessionmanager = SessionManager()
    session = sessionmanager.session
    timestamp = datetime.datetime.now()
    try:
        ip = ipaddress.ip_address(hostmask)
    except ValueError:
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(hostmask))
        except socket.gaierror:
            print(f"Unable to make sense of hostmask: {hostmask}")
    print(f"IP version: {ip.version}")
    if ip.version == 6:
        network = ipaddress.ip_network(f"{hostmask}/56", False)
    else:
        network = ipaddress.ip_network(f"{hostmask}/24", False)
    client = ircsessions.IRCSessions(timestamp=timestamp, nickname=nickname, hostmask=hostmask, network=str(network))
    prevclients = session.query(ircsessions.IRCSessions).filter(or_(ircsessions.IRCSessions.nickname == nickname,
                                                                    ircsessions.IRCSessions.hostmask == hostmask)) \
        .all()
    networks = session.query(ircsessions.IRCSessions).all()
    if prevclients:
        clonenicks = []
        for row in prevclients:

            if row.nickname == client.nickname and row.hostmask == client.hostmask:
                print("Same nick from same IP, update timestamp.")
                row.timestamp = timestamp
                # session.query(ircsessions.IRCSessions).filter(ircsessions.IRCSessions.id == row.id). \
                #     update({'timestamp': timestamp})
                # This update should be committable through the row itself.
                session.commit()
                if withdate:
                    return None, None
                return None
            elif row.nickname == client.nickname and row.hostmask != client.hostmask:
                print("Same nick from different IP, store!")
                session.add(client)
                session.commit()
                if withdate:
                    return None, None
                return None
            elif row.nickname != client.nickname and row.hostmask == client.hostmask:
                print("Different nick from same IP, report!")
                if withdate:
                    lasttime = row.timestamp
                clonenicks.append(row.nickname)
                session.add(client)
                session.commit()
            elif row.hostmask in networks.network:
                print("Same network!")
        if clonenicks:
            set_unique = set(clonenicks)
            clones = list(set_unique)
            print(f"Clones: {clones} Lasttime: {lasttime}")
            if withdate:
                return clones, lasttime
            else:
                return clones
        else:
            if withdate:
                return None, None
            else:
                return None
    else:
        session.add(client)
        session.commit()
        retention_time: int = int(SessionHandler.retention_time)
        timeout = datetime.datetime.now() - datetime.timedelta(days=retention_time)
        oldrecords = session.query(ircsessions.IRCSessions). \
            filter(ircsessions.IRCSessions.timestamp < timeout)
        if oldrecords.count() > 0:
            print(f"Deleting {oldrecords.count()} old sessions.")
            session.query(ircsessions.IRCSessions). \
                filter(ircsessions.IRCSessions.timestamp < timeout).delete()
            session.commit()
        if withdate:
            return None, None
        return None


async def check_clone(bot: fido, nickname, hostmask):
    """
    Handle connection notifications and store sessions.
    :param bot: bot instance
    :param nickname: Nickname of user
    :param hostmask: Hostmask (Or rather just IP) of user
    :return: Nothing.
    """
    sessionmanager = SessionManager()
    session = sessionmanager.session
    print(f"Nick: {nickname} Host: {hostmask}")
    sus_nicks = session.query(monitor.Monitor.nickname).filter(monitor.Monitor.nickname == nickname).one_or_none()
    if sus_nicks:
        print(f"Sus nick found!")
        await bot.message("#rat-ops", f"Monitored nick {nickname} has come online.")

    clonenicks, lasttime = is_clone(nickname, hostmask, True)
    if clonenicks is not None and lasttime is not None:
        set_unique = set(clonenicks)
        clones = list(set_unique)
        await bot.message("#opers",
                          f"{bot.colour_red('CLONE')} {nickname} has connected from {hostmask}, "
                          f"previous nicknames: {', '.join(clones)} (Last connected {lasttime})")


async def get_clones(bot: fido, nickname, hostmask):
    """
    Check whether a nickname is registered as a clone in the DB.
    :param bot: bot instance
    :param nickname: Nickname of user
    :param hostmask: Hostmask (or IP) of user
    :return: A list of previous clone names, or None
    """

    return check_clone(nickname, hostmask)

import fido, datetime, ipaddress

from models import SessionManager
from models import ircsessions
from sqlalchemy import or_


def is_clone(nickname, hostmask):
    """
    Checks whether a nickname is considered a clone by the bot.
    :param hostmask: Hostmask of user
    :param bot: bot instance
    :param nickname: Nickname of user
    :return: A list of nicknames previously used if the user is a clone, or None.
    """
    sessionmanager = SessionManager()
    session = sessionmanager.session
    timestamp = datetime.datetime.now()
    ip = ipaddress.ip_address(hostmask)
    if ip.version == '6':
        network = ipaddress.ip_network(f"{hostmask}/56", False)
    else:
        network = ipaddress.ip_network(f"{hostmask}/24", False)
    client = ircsessions.IRCSessions(timestamp=timestamp, nickname=nickname, hostmask=hostmask, network=str(network))
    prevclients = session.query(ircsessions.IRCSessions).filter(or_(ircsessions.IRCSessions.nickname == nickname,
                                                                    ircsessions.IRCSessions.hostmask == hostmask))\
        .all()
    networks = session.query(ircsessions.IRCSessions).all()
    if prevclients:
        print(f"Got clients!")
        clonenicks = []
        for row in prevclients:

            if row.nickname == client.nickname and row.hostmask == client.hostmask:
                session.query(ircsessions.IRCSessions).filter(ircsessions.IRCSessions.id == row.id).\
                    update({'timestamp': timestamp})
                session.commit()
                return
            elif row.nickname == client.nickname and row.hostmask != client.hostmask:
                print("Same nick from different IP, store!")
                session.add(client)
                session.commit()
                return
            elif row.nickname != nickname and row.hostmask == hostmask:
                print("Different nick from same IP, report!")
                clonenicks.append(row.nickname)
            elif row.hostmask in networks.network:
                print("Same network!")
        if clonenicks:
            set_unique = set(clonenicks)
            clones = list(set_unique)
            return clones
        else:
            return None
    else:
        session.add(client)
        session.commit()
        # TODO: Implement clearing records older than <session_retain_limit> here.
        return None


async def check_clone(bot: fido, nickname, hostmask):
    """
    Handle connection notifications and store sessions.
    :param bot: bot instance
    :param nickname: Nickname of user
    :param hostmask: Hostmask (Or rather just IP) of user
    :return: Nothing.
    """

    clonenicks = check_clone(nickname, hostmask)
    if clonenicks is not None:
        set_unique = set(clonenicks)
        clones = list(set_unique)
        await bot.message("#opers",
                          f"{bot.colour_red('CLONE')} {nickname} has connected from {hostmask}, "
                          f"previous nicknames: {', '.join(clones)}")


async def get_clones(bot: fido, nickname, hostmask):
    """
    Check whether a nickname is registered as a clone in the DB.
    :param bot: bot instance
    :param nickname: Nickname of user
    :param hostmask: Hostmask (or IP) of user
    :return: A list of previous clone names, or None
    """

    return check_clone(nickname, hostmask)

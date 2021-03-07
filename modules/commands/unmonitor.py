from typing import List
from config import IRC
import fido

from modules.access import require_permission, Levels
from models import SessionManager
from models import monitor
import logging

log = logging.getLogger(__name__)


@require_permission(level=Levels.OP, message='DENIED!')
async def invoke(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !unmonitor command
    :param channel: Channel the command is invoked in
    :param sender: Sender of the IRC command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    sessionmanager = SessionManager()
    session = sessionmanager.session

    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "unmonitor <username>"

    nick = args[0]
    res = session.query(monitor.Monitor).filter(monitor.Monitor.nickname == nick).one_or_none()
    if res:
        await bot.message(channel, f"Stopped monitoring for {nick}.")
        try:
            session.query(monitor.Monitor).filter(monitor.Monitor.nickname == nick).delete()
            session.commit()
            log.info(f"{sender} stopped monitoring for {nick}")
        except:
            print("Failed to delete monitor row!")
            session.rollback()

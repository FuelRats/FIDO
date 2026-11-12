from typing import List
from config import IRC
import fido

from modules.access import require_permission, Levels
from models import monitor, session_scope
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
    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "unmonitor <username>"

    nick = args[0]
    with session_scope() as session:
        res = session.query(monitor.Monitor).filter(monitor.Monitor.nickname == nick).one_or_none()
    if res:
        await bot.message(channel, f"Stopped monitoring for {nick}.")
        try:
            with session_scope() as session:
                session.query(monitor.Monitor).filter(monitor.Monitor.nickname == nick).delete()
            log.info(f"{sender} stopped monitoring for {nick}")
        except:
            log.exception("Failed to delete monitor row!")

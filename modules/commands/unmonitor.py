from typing import List

from sqlalchemy.exc import SQLAlchemyError

from config import IRC
import fido

from modules.access import require_oper
from models import monitor, session_scope
import logging

log = logging.getLogger(__name__)


@require_oper("stop monitoring nicks")
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
    try:
        with session_scope() as session:
            removed = session.query(monitor.Monitor).filter(monitor.Monitor.nickname == nick).delete()
    except SQLAlchemyError:
        log.exception("Failed to delete monitor rows!")
        await bot.message(channel, "Database error while removing monitor nick.")
        return
    if not removed:
        await bot.message(channel, f"I am not monitoring for {nick}.")
        return
    await bot.unmonitor(nick)
    log.info(f"{sender} stopped monitoring for {nick}")
    await bot.message(channel, f"Stopped monitoring for {nick}.")

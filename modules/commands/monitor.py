import logging
from datetime import datetime
from typing import List

from sqlalchemy.exc import SQLAlchemyError

from config import IRC
import fido

from modules.access import require_oper
from models import monitor, session_scope

log = logging.getLogger(__name__)


@require_oper("monitor nicks")
async def invoke(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !monitor command
    :param channel: Channel the command is invoked in
    :param sender: Sender of the IRC command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "monitor <username> <message>"

    nick = args[0]
    message = ' '.join(args[1:])
    reason = f"Reason: {message} ({sender})" if message else f"No reason given ({sender})"
    try:
        with session_scope() as session:
            if session.query(monitor.Monitor).filter(monitor.Monitor.nickname == nick).first() is not None:
                duplicate = True
            else:
                duplicate = False
                session.add(monitor.Monitor(timestamp=datetime.now(), nickname=nick, msg=reason))
    except SQLAlchemyError:
        log.exception("Failed to insert!")
        await bot.message(channel, "Database error while adding monitor nick.")
        return
    if duplicate:
        await bot.message(channel, f"I am already monitoring for {nick}.")
        return
    await bot.monitor(nick)
    if nick in bot.users:
        await bot.message(channel, f"I am now monitoring for {nick} and possible clones.")
    else:
        await bot.message(channel, "Nickname not found online, but I'll keep an eye out for that exact name.")

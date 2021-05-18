from datetime import datetime
from typing import List
from config import IRC
import requests
import ipaddress
import fido
from requests.exceptions import SSLError
from OpenSSL.SSL import Error

from modules.access import require_permission, Levels
from models import monitor
from models import SessionManager
from config import SessionHandler


@require_permission(level=Levels.OP, message='DENIED!')
async def invoke(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !monitor command
    :param channel: Channel the command is invoked in
    :param sender: Sender of the IRC command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    sessionmanager = SessionManager()
    session = sessionmanager.session

    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "monitor <username> <message>"

    lines = []
    nick = args[0]
    message = ' '.join(args[1:])
    timestamp = datetime.now()
    if nick in bot.users:
        whois = await bot.whois(nick)
        ip = bot.users[nick]['real_ip_address']
        mon = monitor.Monitor(timestamp=timestamp, nickname=nick, msg=f"Reason: {message} ({sender})"
                                                                      or f"No reason given ({sender})")
        try:
            session.add(mon)
            session.commit()
            bot.monitor(nick)
        except:
            print("Failed to insert!")
            session.rollback()
        await bot.message(channel, f"I am now monitoring for {nick} and possible clones.")
    else:
        await bot.message(channel, f"Nickname not found online, but I'll keep an eye out for that exact name.")

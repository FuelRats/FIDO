from typing import List
from config import IRC
import requests
import ipaddress
import fido
from modules.access import require_permission, Levels
from models import config, SessionManager
import logging
import re

log = logging.getLogger(__name__)


@require_permission(level=Levels.OP, message='DENIED!')
async def invoke(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Mute/Unmute a nick.
    :param bot: Bot reference
    :param channel: Channel the command is invoked in
    :param sender: Who invoked the command
    :param args: Who to mute
    :return: Reply message.
    """
    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "mute <x>[m|h|d] <nickname>"

    time_pattern = re.compile(r'(\d+)([mhd])')
    time_arg = args[0]
    match = time_pattern.match(time_arg)

    if match:
        time_value = int(match.group(1))
        time_unit = match.group(2)
        if time_unit == 'm':
            mutetime = time_value
        elif time_unit == 'h':
            mutetime = time_value * 60
        elif time_unit == 'd':
            mutetime = time_value * 1440
        args = args[1:]
    else:
        session = SessionManager().session
        mutetime = session.query(config.Config).filter_by(module='channelprotection',
                                                          key='mutetime').one_or_none().value or 6

    log.debug(f"Processing {args}")
    for arg in args:
        if arg == "":
            continue
        if arg in bot.users:
            await bot.set_mode(channel, "-v", f"{bot.users[arg]['nickname']}")
            await bot.set_mode(channel, "+b", f"~t:{mutetime}:~quiet:*!*@{bot.users[arg]['hostname']}")
            await bot.message(channel, f"Muted {bot.users[arg]['nickname']} for {mutetime} minutes.")
            log.info(f"{bot.users[arg]['nickname']} was muted for {mutetime} minutes by {sender}")
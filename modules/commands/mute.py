from typing import List
from config import IRC
import fido
from modules.access import require_permission, Levels
from modules import configmanager
import logging
import re

log = logging.getLogger(__name__)

TIME_PATTERN = re.compile(r'(\d+)([mhd])')
MINUTES_PER_UNIT = {'m': 1, 'h': 60, 'd': 1440}
MAX_MUTE_MINUTES = 9999  # UnrealIRCd's limit for ~time bans


def mute_mask(minutes: int, hostname: str) -> str:
    """The timed quiet ban, in the named form UnrealIRCd stores and lists."""
    return f"~time:{minutes}:~quiet:*!*@{hostname}"


@require_permission(level=Levels.OP, message='You must be a channel operator to mute.')
async def invoke(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Mute a nick.
    :param bot: Bot reference
    :param channel: Channel the command is invoked in
    :param sender: Who invoked the command
    :param args: Who to mute
    :return: Reply message.
    """
    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "mute <x>[m|h|d] <nickname>"

    match = TIME_PATTERN.fullmatch(args[0])
    if match:
        mutetime = int(match.group(1)) * MINUTES_PER_UNIT[match.group(2)]
        args = args[1:]
    else:
        mutetime = int(configmanager.get_value('channelprotection', 'mutetime'))
    if not 1 <= mutetime <= MAX_MUTE_MINUTES:
        return f"Mute time must be between 1 and {MAX_MUTE_MINUTES} minutes; {mutetime} is not."

    log.debug(f"Processing {args}")
    for arg in args:
        if arg == "":
            continue
        if arg in bot.users:
            await bot.set_mode(channel, "-v", f"{bot.users[arg]['nickname']}")
            await bot.set_mode(channel, "+b", mute_mask(mutetime, bot.users[arg]['hostname']))
            await bot.message(channel, f"Muted {bot.users[arg]['nickname']} for {mutetime} minutes.")
            log.info(f"{bot.users[arg]['nickname']} was muted for {mutetime} minutes by {sender}")

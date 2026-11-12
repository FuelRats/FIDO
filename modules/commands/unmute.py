import re
from typing import List
from config import IRC
import fido
from modules.access import require_permission, Levels
import logging

log = logging.getLogger(__name__)


def mute_entries(bot: fido, channel: str, hostname: str) -> List[str]:
    """The channel's ban list entries that are timed mutes of *!*@hostname, as the server stores them."""
    pattern = re.compile(rf"~time:\d+:~quiet:\*!\*@{re.escape(hostname)}", re.IGNORECASE)
    bans = bot.channels[channel]['modes'].get('b', [])
    return [entry for entry in bans if pattern.fullmatch(entry)]


@require_permission(level=Levels.HALFOP, message='You must be a half-op or higher to unmute.')
async def invoke(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Unmute a nick: remove every timed mute of its host from the channel's ban list.
    :param bot: Bot reference
    :param channel: Channel the command is invoked in
    :param sender: Who invoked the command
    :param args: Who to unmute
    :return: Reply message.
    """
    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "unmute <nickname>"
    log.debug(f"Processing {args}")
    for arg in args:
        if arg == "":
            continue
        user = bot.users.get(arg)
        entries = mute_entries(bot, channel, user['hostname']) if user and user.get('hostname') else []
        if not entries:
            await bot.message(channel, f"{arg}: no matching mute.")
            continue
        for entry in entries:
            await bot.set_mode(channel, "-b", entry)
        await bot.message(channel, f"Unmuted {user['nickname']}.")
        log.info(f"{sender} unmuted {user['nickname']} in {channel}.")

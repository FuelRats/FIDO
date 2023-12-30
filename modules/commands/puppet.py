from typing import List

import fido
from config import IRC
from modules import configmanager
from modules.access import Levels, get_access_level


def get_channel(bot: fido, channel: str):
    if channel in bot.channels:
        return channel
    return None


async def puppet(bot: fido, sender: str, args: List[str], is_act: bool):
    if len(args) < 2:
        command = "act" if is_act else "say"
        return f"Usage: {IRC.commandPrefix}{command} <channel> <message>"

    hostname = bot.users[sender]["hostname"]
    channel = get_channel(bot, args[0])
    message = ' '.join(args[1:])
    try:
        permission_channel = configmanager.get_config("channels", "puppet_permission")[0]
    except IndexError:
        return

    if get_access_level(bot, permission_channel, sender).value <= Levels.OP.value:
        return "Permission denied"

    if channel is None:
        return "Invalid channel"

    if is_act:
        await bot.ctcp(channel, "ACTION", contents=message)
    else:
        await bot.message(channel, message)


async def act(bot: fido, sender: str, args: List[str]):
    return await puppet(bot, sender, args, True)


async def say(bot: fido, sender: str, args: List[str]):
    return await puppet(bot, sender, args, False)

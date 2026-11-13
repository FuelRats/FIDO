from typing import List

import fido
from config import IRC
from modules.access import is_irc_operator


def get_channel(bot: fido, channel: str):
    if channel in bot.channels:
        return channel
    return None


async def puppet(bot: fido, sender: str, args: List[str], is_act: bool):
    command = "act" if is_act else "say"
    if len(args) < 2:
        return f"Usage: {IRC.commandPrefix}{command} <channel> <message>"

    channel = get_channel(bot, args[0])
    message = ' '.join(args[1:])

    if not await is_irc_operator(bot, sender):
        return f"You must be an IRC operator to use {IRC.commandPrefix}{command}."

    if channel is None:
        return "Invalid channel"

    if is_act:
        await bot.ctcp(channel, "ACTION", message)
    else:
        await bot.message(channel, message)


async def act(bot: fido, sender: str, args: List[str]):
    return await puppet(bot, sender, args, True)


async def say(bot: fido, sender: str, args: List[str]):
    return await puppet(bot, sender, args, False)

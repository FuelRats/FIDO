from typing import List

import fido


def get_channel(bot: fido, channel: str):
    if channel in bot.channels:
        return channel
    return None


async def act(bot: fido, channel: str, sender: str, args: List[str]):
    channel = get_channel(channel)
    message = ', '.join(args[1:])
    if channel is None:
        return
    if message is None:
        return
    await bot.act(channel, message)


async def say(bot: fido, channel: str, sender: str, args: List[str]):
    channel = get_channel(channel)
    message = ', '.join(args[1:])
    if channel is None:
        return
    if message is None:
        return
    await bot.act(channel, message)

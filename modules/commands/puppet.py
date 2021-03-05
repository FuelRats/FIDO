from typing import List

import fido


def get_channel(bot: fido, channel: str):
    if channel in bot.channels:
        return channel
    return None


async def act(bot: fido, channel: str, sender: str, args: List[str]):
    channel = get_channel(bot, channel)
    print("I'm gonna woof!")
    message = ' '.join(args)
    if channel is None:
        return
    if message is None:
        return
    await bot.act(channel, f":ACTION {message}")


async def say(bot: fido, channel: str, sender: str, args: List[str]):
    channel = get_channel(bot, channel)
    message = ' '.join(args)
    if channel is None:
        return
    if message is None:
        return
    await bot.message(channel, message)

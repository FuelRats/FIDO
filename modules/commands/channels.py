from typing import List

import fido


async def join_channel(bot: fido, args: List[str]):
    """
    Handler for the !join command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    channels: List[str] = []
    for arg in args:
        if arg.startswith('#'):
            channels.append(arg)
            await bot.join(arg)
    return f"Joined: {', '.join(channels)}."


async def part_channel(bot: fido, args: List[str]):
    """
    Handler for the !part command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    channels: List[str] = []
    for arg in args:
        if arg.startswith('#'):
            channels.append(arg)
            await bot.part(arg)
    return f"Parted: {', '.join(channels)}."

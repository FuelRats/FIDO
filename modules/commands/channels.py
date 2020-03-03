from typing import List

import fido
from models import SessionManager, config


async def join_channel(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !join command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    session = SessionManager().session
    channels: List[str] = []
    for arg in args:
        if arg.startswith('#') and arg not in bot.channels:
            channels.append(arg)
            await bot.join(arg)
            newchannel = config.Config(module='channels', key='join', value=arg)
            session.add(newchannel)
    session.commit()
    if len(channels) > 0:
        await bot.message(channel, f"Joined: {', '.join(channels)}.")


async def part_channel(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !part command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    session = SessionManager().session
    channels: List[str] = []
    for arg in args:
        if arg.startswith('#') and arg in bot.channels:
            channels.append(arg)
            await bot.part(arg)
            session.query(config.Config).filter_by(module='channels', key='join', value=arg).delete()
    session.commit()
    if len(channels) > 0:
        await bot.message(channel, f"Parted: {', '.join(channels)}.")

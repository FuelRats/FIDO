from typing import List

import fido
from modules.access import require_permission, Levels
from models import config, session_scope


@require_permission(level=Levels.OP, message='You must be an op to make FIDO join channels.')
async def join_channel(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !join command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    channels: List[str] = []
    for arg in args:
        if arg.startswith('#') and arg not in bot.channels:
            channels.append(arg)
            await bot.join(arg)
    with session_scope() as session:
        for joined in channels:
            session.add(config.Config(module='channels', key='join', value=joined))
    if len(channels) > 0:
        await bot.message(channel, f"Joined: {', '.join(channels)}.")


@require_permission(level=Levels.OP, message='You must be an op to make FIDO join channels.')
async def part_channel(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !part command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    channels: List[str] = []
    for arg in args:
        if arg.startswith('#') and arg in bot.channels:
            channels.append(arg)
            await bot.part(arg)
    with session_scope() as session:
        for parted in channels:
            session.query(config.Config).filter_by(module='channels', key='join', value=parted).delete()
    if len(channels) > 0:
        await bot.message(channel, f"Parted: {', '.join(channels)}.")

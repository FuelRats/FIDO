import asyncio
from typing import List

import fido
from modules.access import require_oper
from models import config, session_scope

JOIN_CONFIRM_TIMEOUT = 10  # seconds to wait for the server's echo of FIDO's JOIN; read at use time


@require_oper("make FIDO join channels")
async def join_channel(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !join command. A channel is remembered only once the server confirmed the join.
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """
    unique = {}  # one join per channel, however it is spelled
    for arg in args:
        if arg.startswith('#') and arg not in bot.channels:
            unique.setdefault(bot.normalize(arg), arg)
    wanted = list(unique.values())
    if not wanted:
        return
    confirmed = await asyncio.gather(*(bot.join_confirmed(arg, JOIN_CONFIRM_TIMEOUT) for arg in wanted))
    channels = [arg for arg, ok in zip(wanted, confirmed) if ok]
    failed = [arg for arg, ok in zip(wanted, confirmed) if not ok]
    with session_scope() as session:
        for joined in channels:
            session.add(config.Config(module='channels', key='join', value=joined))
    if len(channels) > 0:
        await bot.message(channel, f"Joined: {', '.join(channels)}.")
    if failed:
        await bot.message(channel, f"Could not join within {JOIN_CONFIRM_TIMEOUT} s, not remembered: "
                                   f"{', '.join(failed)}.")


@require_oper("make FIDO part channels")
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

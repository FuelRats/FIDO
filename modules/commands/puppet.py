from typing import List

import fido
from config import IRC
from models import SessionManager, config
from modules import configmanager
from modules.access import require_permission, Levels


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
    operchannel = bot.get_oper_channel()

    if hostname not in configmanager.get_config("puppet", "authorizedhost"):
        return f"Permission denied"

    if channel is None:
        return "Invalid channel"

    await bot.message(operchannel, f"Puppet in {channel} by {sender}")

    if is_act:
        await bot.ctcp(channel, "ACTION", contents=message)
    else:
        await bot.message(channel, message)


async def act(bot: fido, sender: str, args: List[str]):
    return await puppet(bot, sender, args, True)


async def say(bot: fido, sender: str, args: List[str]):
    return await puppet(bot, sender, args, False)


@require_permission(level=Levels.OP, message="Permission denied!")
async def authorize_host(bot: fido, channel: str, sender: str,
                         args: List[str]):
    if len(args) != 1:
        return f"Usage: {IRC.commandPrefix}puppet_allow <host>"

    host = args[0]

    session = SessionManager().session
    authorized_host = config.Config(module='puppet', key='authorizedhost', value=host)
    session.add(authorized_host)
    session.commit()
    return f"Host {host} may now use the puppet module"


@require_permission(level=Levels.OP, message="Permission denied!")
async def deauthorize_host(bot: fido, channel: str, sender: str,
                           args: List[str]):
    if len(args) != 1:
        return f"Usage: {IRC.commandPrefix}puppet_disallow <host>"

    host = args[0]

    session = SessionManager().session
    session.query(config.Config).filter_by(module='puppet', key='authorizedhost', value=host).delete()
    session.commit()
    return f"Host {host} may no longer use the puppet module"

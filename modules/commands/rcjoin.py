from typing import List
from config import IRC

import fido

from modules.access import require_oper
import logging

log = logging.getLogger(__name__)


@require_oper("!rcjoin clients")
async def rcjoin(bot: fido, channel: str, sender: str, args: List[str]):
    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "rcjoin <client name>"
    for arg in args:
        if arg in bot.users:
            await bot.message(channel, f"{arg} is being joined to #ratchat.")
            await bot.raw(f"SAJOIN {arg} #ratchat\n")

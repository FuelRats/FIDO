from typing import List
from config import IRC
import fido

from modules.access import require_permission, Levels
import logging

log = logging.getLogger(__name__)


@require_permission(level=Levels.VOICE, message='You must be a drilled rat to !rcjoin clients.')
async def rcjoin(bot: fido, channel: str, sender: str, args: List[str]):
    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "rcjoin <client name>"
        if args in bot.users:
            await bot.message(channel, f"{args} is being joined to #ratchat.")
            await bot.raw(f"SAJOIN {args} #ratchat\n")

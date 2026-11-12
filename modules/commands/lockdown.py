from typing import List
import fido
from modules.access import require_oper
from modules import configmanager
from modules.channelprotections.droneprotection import LOCKDOWN_BAN, LOCKDOWN_CHANNEL, LOCKDOWN_ON, LOCKDOWN_STATE, \
    in_lockdown

import logging

log = logging.getLogger(__name__)


@require_oper("lock down #ratchat")
async def lockdown(bot: fido, channel: str, sender: str, args: List[str]):
    if in_lockdown():
        await bot.message(channel, "LOCKDOWN: Lockdown is already in effect.")
    else:
        await bot.message(channel, "LOCKDOWN: Locking down!")
        await bot.message(LOCKDOWN_CHANNEL, "*** LOCKDOWN INITIATED *** Manual lockdown initiated, "
                                            "new connections failing drone scans will now be G-Lined and "
                                            "non-clients redirected to #NewRats. This may cause some "
                                            "clients to not be able to connect.")
        await bot.rawmsg('MODE', LOCKDOWN_CHANNEL, '+b', LOCKDOWN_BAN)
        configmanager.set_config(*LOCKDOWN_STATE, LOCKDOWN_ON)
        log.info(f"{sender} started a lockdown")


@require_oper("lift a lockdown")
async def disable_lockdown(bot: fido, channel: str, sender: str, args: List[str]):

    if not in_lockdown():
        await bot.message(channel, "LOCKDOWN: Lockdown isn't enabled, doing nothing.")
    else:
        await bot.message(channel, "LOCKDOWN: Restoring normal operations.")
        await bot.message(LOCKDOWN_CHANNEL, "*** LOCKDOWN CLEARED *** Normal operations resumed. Channel "
                                            "join restrictions lifted, non-clients will now directly "
                                            "join #ratchat.")
        await bot.rawmsg('MODE', LOCKDOWN_CHANNEL, '-b', LOCKDOWN_BAN)
        configmanager.del_config(*LOCKDOWN_STATE)
        log.info(f"{sender} lifted a lockdown")

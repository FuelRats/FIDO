from typing import List
from config import IRC
import requests
import ipaddress
import fido
from modules.access import require_permission, Levels
from models import SessionManager, config
from modules import configmanager

import logging

log = logging.getLogger(__name__)


@require_permission(level=Levels.OP, message='DENIED!')
async def lockdown(bot: fido, channel: str, sender: str, args: List[str]):
    ldstatus = configmanager.get_config('droneprotection', 'lockdown')
    if ldstatus:
        await bot.message(channel, "LOCKDOWN: Lockdown is already in effect.")
    else:
        await bot.message(channel, "LOCKDOWN: Locking down!")
        await bot.message("#ratchat", f"*** LOCKDOWN INITIATED *** Manual lockdown initiated, "
                                      f"new connections failing drone scans will now be KILLed and "
                                      f"non-clients redirected to #NewRats. This may cause some "
                                      f"clients to not be able to connect.")
        await bot.raw(f"MODE #ratchat +b ~f:#NewRats:~G:unknown-users\n")
        configmanager.set_config('droneprotection', 'lockdown', "True")


@require_permission(level=Levels.OP, message='DENIED!')
async def disable_lockdown(bot: fido, channel: str, sender: str, args: List[str]):

    ldstatus = configmanager.get_config('droneprotection', 'lockdown')
    if not ldstatus:
        await bot.message(channel, "LOCKDOWN: Lockdown isn't enabled, doing nothing.")
    else:
        await bot.message(channel, "LOCKDOWN: Restoring normal operations.")
        await bot.message("#ratchat", f"*** LOCKDOWN CLEARED *** Normal operations resumed. Channel "
                                      f"join restrictions lifted, non-clients will now directly "
                                      f"join #ratchat.")
        await bot.raw(f"MODE #ratchat -b ~f:#NewRats:~G:unknown-users\n")
        configmanager.del_config('droneprotection', 'lockdown')

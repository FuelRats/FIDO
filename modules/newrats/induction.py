import re
import fido
from modules import sessiontracker
from modules.networkprotection import asn_blacklist


async def on_join(bot: fido, channel: str, user: str):
    if channel == '#NewRats':
        await bot.message(channel, f"{user}: Welcome to the Fuel Rats! If you are on emergency oxygen "
                                   f"please log out to main menu.  If you need fuel, please let us know "
                                   f"as soon as possible.  If you are interested in joining the cause, "
                                   f"check out: https://t.fuelr.at/join .  If you're already a rat, or "
                                   f"are a new recruit, please identify using the information below.")
        await bot.message(channel, f"Switch to the FuelRats tab in the top left corner (Or your Status "
                                   f"window) and identify with NickServ with the following command, but "
                                   f"replace <password> with your password: /msg NickServ IDENTIFY "
                                   f"<password>")

import time

import fido
from modules import configmanager

GREETING_CHANNEL = '#NewRats'
GREETING_MEMORY = 24 * 60 * 60  # seconds a greeted nick is not greeted again


def forget_old_greetings(bot: fido, now: float):
    for nick, greeted in list(bot.recent_greeting.items()):
        if now - greeted >= GREETING_MEMORY:
            del bot.recent_greeting[nick]


async def on_join(bot: fido, channel: str, user: str):
    if bot.normalize(channel) != bot.normalize(GREETING_CHANNEL):
        return
    if not configmanager.gate_open(configmanager.GATE_NEWRATS_GREETING):
        return
    now = time.monotonic()
    forget_old_greetings(bot, now)
    if bot.normalize(user) in bot.recent_greeting:
        return  # Skip recently greeted users.
    whois = await bot.whois(user)
    if whois is None:
        return  # Gone before the WHOIS answered.
    if whois.get('identified'):
        return  # Skip identified users.
    await bot.message(channel, f"{user}: Welcome to the Fuel Rats! If you are on emergency oxygen "
                               f"please log out to main menu.  If you need fuel, please let us know "
                               f"as soon as possible.  If you are interested in joining the cause, "
                               f"check out: https://t.fuelr.at/join .  If you're already a rat, or "
                               f"are a new recruit, please identify using the information below.")
    await bot.message(channel, "Switch to the FuelRats tab in the top left corner (Or your Status "
                               "window) and identify with NickServ with the following command, but "
                               "replace <password> with your password: /msg NickServ IDENTIFY "
                               "<password>")
    bot.recent_greeting[bot.normalize(user)] = now

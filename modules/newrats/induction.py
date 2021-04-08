import fido


async def on_join(bot: fido, channel: str, user: str):
    if user == 'FIDO[BOT]':
        return  # Yah, don't greet yourself, you silly bot.
    if channel == '#NewRats':
        whois = await bot.whois(user)
        if whois['identified']:
            return  # Skip identified users.
        await bot.message(channel, f"{user}: Welcome to the Fuel Rats! If you are on emergency oxygen "
                                   f"please log out to main menu.  If you need fuel, please let us know "
                                   f"as soon as possible.  If you are interested in joining the cause, "
                                   f"check out: https://t.fuelr.at/join .  If you're already a rat, or "
                                   f"are a new recruit, please identify using the information below.")
        await bot.message(channel, f"Switch to the FuelRats tab in the top left corner (Or your Status "
                                   f"window) and identify with NickServ with the following command, but "
                                   f"replace <password> with your password: /msg NickServ IDENTIFY "
                                   f"<password>")

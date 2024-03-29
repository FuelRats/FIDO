import fido
from config import IRC
from modules import configmanager
from modules.commands import fetch, channels, puppet, mute, unmute, nexmo, monitor, \
    unmonitor, asn_ban, rcjoin, lockdown, stonks

commandsDict = {
    "fetch": fetch.invoke,
    "geoip": fetch.invoke,
    "join": channels.join_channel,
    "part": channels.part_channel,
    "mute": mute.invoke,
    "unmute": unmute.invoke,
    "nexmoadd": nexmo.groupadd,
    "nexmosend": nexmo.sendmessage,
    "monitor": monitor.invoke,
    "watch": monitor.invoke,
    "unmonitor": unmonitor.invoke,
    "asn_ban": asn_ban.ban_asn,
    "asn_test": asn_ban.test_asn,
    "asn_unban": asn_ban.unban_asn,
    "rcjoin": rcjoin.rcjoin,
    "lockdown": lockdown.lockdown,
    "unlock": lockdown.disable_lockdown,
    "value": stonks.crypto_value,
    "compare": stonks.crypto_compare,
    "ticker": stonks.ticker_info,
}

privateCommandsDict = {
    "act": puppet.act,
    "say": puppet.say
}


async def on_channel_message(bot: fido, channel: str, sender: str, message: str):
    """
    General Message Handler
    :param bot: bot instance
    :param channel: channel the message was in
    :param sender: nick that sent the message
    :param message: The Message received
    :return: the reply to be sent to the sender
    """
    if message.startswith(IRC.commandPrefix):
        bot_hosts = configmanager.get_config("commandhandler", "bothost")
        if bot.users[sender]["hostname"] in bot_hosts:
            # Ignore commands sent by other bots
            return
        parts = message[1:].split(" ")
        command = parts[0]
        arguments = parts[1:]

        # Start Commands
        if command in commandsDict:
            output = await commandsDict[command](bot, channel, sender, arguments)
            if output:
                await bot.message(channel, output)


async def on_private_message(bot: fido, sender: str, message: str):
    if not message.startswith(IRC.commandPrefix):
        # TODO: tell about unknown command if in DM
        # bot message "unknown Command"
        return

    parts = message[1:].split(" ")
    command = parts[0]
    arguments = parts[1:]

    if command in privateCommandsDict:
        output = await privateCommandsDict[command](bot, sender, arguments)
        if output:
            await bot.message(sender, output)

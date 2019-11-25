import fido
from config import IRC
from modules.commands import fetch, channels, puppet

commandsDict = {
    "fetch": fetch.invoke,
    "join": channels.join_channel,
    "part": channels.part_channel
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
        parts = message[1:].split(" ")
        command = parts[0]
        arguments = parts[1:]

        # Start Commands
        if command in commandsDict:
            return await commandsDict[command](bot, channel, sender, arguments)
        else:
            return False


async def on_private_message(bot: fido, sender: str, message: str):
    if not message.startswith(IRC.commandPrefix):
        # TODO: tell about unknown command if in DM
        # bot message "unknown Command"
        return

    parts = message[1:].split(" ")
    command = parts[0]
    channel = parts[1]
    arguments = parts[2:]

    if command in commandsDict:
        return await commandsDict[command](bot, channel, sender, arguments)
    elif command in privateCommandsDict:
        return await privateCommandsDict[command](bot, channel, sender, arguments)

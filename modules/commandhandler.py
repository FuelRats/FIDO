import fido
from config import IRC
from modules.commands import fetch, channels


commandsDict = {
        "fetch": fetch.invoke,
        "join": channels.join_channel,
        "part": channels.part_channel
    }


async def handle_command(bot: fido, message: str):
    """
    General Message Handler
    :param bot: bot instance
    :param message: The Message received
    :return: the reply to be sent to the sender
    """
    if message.startswith(IRC.commandPrefix):
        parts = message[1:].split(" ")
        command = parts[0]
        arguments = parts[1:]

        # Start Commands
        if command in commandsDict:
            return await commandsDict[command](bot, arguments)
        else:
            return False
            # TODO: tell about unknown command if in DM
            # return "unknown Command"

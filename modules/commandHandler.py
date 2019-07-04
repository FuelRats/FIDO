from config import IRC
from modules.commands import fetch


commandsDict = {"fetch": fetch.invoke}


def handleCommand(message: str):
    """
    General Message Handler
    :param message: The Message received
    :return: the reply to be sent to the sender
    """
    if message.startswith(IRC.commandPrefix):
        parts = message[1:].split(" ")
        command = parts[0]
        arguments = parts[1:]

        # Start Commands
        if command in commandsDict:
            return commandsDict[command](arguments)
        else:
            return False
            # TODO: tell about unknown command if in DM
            # return "unknown Command"

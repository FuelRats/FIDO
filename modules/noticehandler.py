import re

import fido
from modules.notices import kill

noticesDict = {
    kill.regex: kill.on_kill
}


async def handle_notice(bot: fido, message: str):
    """
    General Notice Handler
    :param bot: bot instance
    :param message: The Message received
    :return: the reply to be sent to the sender
    """

    for key in noticesDict:
        match = re.match(key, message)
        if match:
            await noticesDict[key](bot, message, match)

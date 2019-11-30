import re

import fido
from modules.notices import kill, connect, oper

noticesDict = {
    kill.regex: kill.on_kill,
    connect.regex: connect.on_connect,
    oper.regex: oper.on_oper_fail
}


async def handle_notice(bot: fido, message: str):
    """
    General Notice Handler
    :param bot: bot instance
    :param message: The Message received
    """

    for key in noticesDict:
        match = re.match(key, message)
        if match:
            await noticesDict[key](bot, message, match)

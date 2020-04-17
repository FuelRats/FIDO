import re

import fido
from modules.notices import kill, connect, oper, spamfilter

noticesDict = {
    kill.regex: kill.on_kill,
    connect.regex: connect.on_connect,
    oper.regex: oper.on_oper_fail,
    spamfilter.regex: spamfilter.on_spamfilter_trigger,
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

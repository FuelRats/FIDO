from typing import List

import fido


async def invoke(bot:fido, args: List[str]):
    """
    Handler for the !fetch command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """

    return "You have invoked the fetch command"

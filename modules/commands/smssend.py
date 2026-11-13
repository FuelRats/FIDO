import logging
from typing import List

import fido
from config import IRC
from modules import sms
from modules.access import require_oper

log = logging.getLogger(__name__)


@require_oper("send SMS")
async def invoke(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !smssend command: publish a text to the SMS topic of a group.
    :param bot: bot instance
    :param channel: Channel the command is invoked in
    :param sender: Sender of the IRC command
    :param args: The group name, then the text
    :return: The reply message
    """
    group = args[0] if args else ''
    text = ' '.join(args[1:]).strip()
    if not group or not text:
        return "Usage: " + IRC.commandPrefix + "smssend <group> <text>"
    log.info(f"{sender} sends an SMS to group {group}")
    if await sms.send_to_group(group, text):
        return f"SMS sent to group {group}."
    return f"SMS to group {group} was not sent; see the log."

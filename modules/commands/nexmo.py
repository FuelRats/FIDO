import fido

from typing import List
from config import IRC
from modules.access import require_permission, Levels
from modules.nexmo import add_group, send_to_group, get_group


@require_permission(level=Levels.OP, message="Permission denied!")
async def sendmessage(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Sends a SMS message to the specified group. Dear gods, you better not abuse this.
    :param bot: Bot instance
    :param channel: Channel where command is invoked
    :param sender: Sender of command
    :param args: List of arguments, should contain group name and message
    :return:
    """
    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "groupadd <groupname> <nickname> <phonenumber>"
    if not get_group(args[0]):
        await bot.message(channel, f"Group not found: {args[0]}")
        return
    send_to_group(args[0], ' '.join(args[1:]))
    await bot.message(channel, "Message sent.")


@require_permission(level=Levels.ADMIN, message="Nope!")
async def groupadd(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Add someone to a group. If the group does not already exist, it is created.
    Phone number should contain full country code, starting with +.
    The user must be in the channel to be added to the SMS group.
    :param bot: Bot instance
    :param channel: Channel where command is invoked
    :param sender: Sender of command
    :param args: List of arguments, should contain group, nickname and phonenumber.
    :return:
    """

    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "groupadd <groupname> <nickname> <phonenumber>"

    lines = []
    print(f"Args: {args}")
    number = ''
    nickname = ''
    group = ''
    for arg in args:
        if arg == "":
            continue  # Ignore blank args.
        print(f"Arg: [{arg.strip()}]")
        if arg.startswith('+'):
            number = arg
        elif arg in bot.users:
            nickname = arg
        else:
            group = arg
    if not group or not nickname or not number:
        await bot.message(channel, "Incorrect command usage. Ensure user is in channel, and that number has +<country code>.")
        return
    add_group(mygroup=group, nickname=nickname, number=number)
    await bot.message(channel, f"Added {nickname} to SMS group {group} with number {number}")

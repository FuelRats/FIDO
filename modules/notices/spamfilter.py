import re
import fido
from modules.nexmo import send_to_group

regex = re.compile("\[Spamfilter\] (?P<nick>[A-Za-z0-9_´|\[\]]*)!(?P<user>[A-Za-z0-9_´|\[\]]*)@(?P<host>[A-Za-z0-9.:_\-]*) matches filter \'(?P<filter>.*)\': \[cmd: PRIVMSG (?P<target>[A-Za-z0-9#_`\[\]]*): '.*'\] \[reason: (?P<message>[A-Za-z0-9]* .*)]")


async def on_spamfilter_trigger(bot: fido, message, match):
    """
    Handler for spamfilter triggers
    :param bot: bot instance
    :param message: message caught
    :param match: The regex match
    :return: Nothing
    """

    operchannel = bot.get_oper_channel()
    nick = match.group('nick')
    host = match.group('host')
    sender = match.group('user')
    filter = match.group('filter')
    message = match.group('message')
    target = match.group('target')

    if "*opsignal*" in filter:
            send_to_group('ops', f"OPSIGNAL by {nick} in {target}: {message}")

    await bot.message(operchannel, f"OPS1GNAL by {nick} in {target}: {message}")
    return

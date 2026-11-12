import datetime
import logging
import fido
from models import messagecounter, session_scope
from modules import configmanager

log = logging.getLogger(__name__)

levels = {
    "q": 5,  # q owner
    "a": 4,  # a admin
    "o": 3,  # o op
    "h": 2,  # h half-op
    "v": 1,  # v voice
    None: 0
}


async def on_message(bot: fido, channel: str, sender: str, message: str):
    kick_reason: str = configmanager.get_value('channelprotection', 'reason')
    maxmessages: int = int(configmanager.get_value('channelprotection', 'maxmessages'))
    retention_time: int = int(configmanager.get_value('channelprotection', 'messageinterval'))

    # Clear buffer of old messages
    delta = datetime.datetime.now() - datetime.timedelta(seconds=retention_time)
    with session_scope() as session:
        session.query(messagecounter.Messagecounter).filter(messagecounter.Messagecounter.timestamp <= delta).delete()
    if sender in ['MechaSqueak[BOT]', 'RatMama[BOT]', 'FIDO[BOT]']:
        # Do not smack the bots, ever. Also, don't add their messages.
        return
    modes = bot.channels[channel]['modes']
    for mode in modes:
        if modes[mode] == True:  # Skip channel modes. Non-empty list being truthy, we test == True.
            continue
        if sender in modes[mode] and levels[mode] > 2:
            log.debug("Ignored because halfop or higher.")
            return
    with session_scope() as session:
        msgs = session.query(messagecounter.Messagecounter).filter(messagecounter.Messagecounter.nickname == sender).count()
    log.debug(f"Msgcount: {msgs}")
    # TODO: This should honestly get us the modes for the user, but apparently not?
    # uinfo = await bot.whois(sender)
    # log.debug(f"Userinfo: {uinfo}")

    if msgs > maxmessages:

        await bot.kick(channel, sender, kick_reason)
        await bot.message("#opers", f"{sender} was kicked from {channel} for spamming.")
    msg = messagecounter.Messagecounter(timestamp=datetime.datetime.now(), nickname=sender, hostmask=sender, msg='Placeholder')
    with session_scope() as session:
        session.add(msg)

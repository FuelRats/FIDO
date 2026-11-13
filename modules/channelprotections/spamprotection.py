import datetime
import logging
import fido
from models import messagecounter, session_scope
from modules import configmanager
from modules.access import Levels, channel_state, get_access_level

log = logging.getLogger(__name__)


async def on_message(bot: fido, channel: str, sender: str, message: str):
    if channel_state(bot, channel, "flood check skipped") is None:
        return
    kick_reason: str = (configmanager.get_value('channelprotection', 'reason_flood')
                        or configmanager.get_value('channelprotection', 'reason'))
    maxmessages: int = int(configmanager.get_value('channelprotection', 'maxmessages'))
    retention_time: int = int(configmanager.get_value('channelprotection', 'messageinterval'))

    # Clear buffer of old messages
    delta = datetime.datetime.now() - datetime.timedelta(seconds=retention_time)
    with session_scope() as session:
        session.query(messagecounter.Messagecounter).filter(messagecounter.Messagecounter.timestamp <= delta).delete()
    if sender in ['MechaSqueak[BOT]', 'RatMama[BOT]', 'FIDO[BOT]']:
        # Do not smack the bots, ever. Also, don't add their messages.
        return
    if get_access_level(bot, channel, sender).value >= Levels.HALFOP.value:
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

import time
from typing import List
import datetime
import fido
from models import config, SessionManager, messagecounter
from modules.access import require_permission, Levels

levels = {
    "q": 5,  # q owner
    "a": 4,  # a admin
    "o": 3,  # o op
    "h": 2,  # h half-op
    "v": 1,  # v voice
    None: 0
}


async def on_message(bot: fido, channel: str, sender: str, message: str):
    session = SessionManager().session
    kick_reason: str = session.query(config.Config).filter_by(module='channelprotection', key='reason')[0].value
    maxmessages: int = int(
        session.query(config.Config).filter_by(module='channelprotection', key='maxmessages')[0].value)
    retention_time: int = int(
        session.query(config.Config).filter_by(module='channelprotection', key='messageinterval')[0].value)

    # Clear buffer of old messages
    delta = datetime.datetime.now() - datetime.timedelta(seconds=retention_time)
    print(f"Timeout: {delta}")
    session.query(messagecounter.Messagecounter).filter(messagecounter.Messagecounter.timestamp <= delta).delete()
    session.commit()
    if sender in ['MechaSqueak[BOT]', 'RatMama[BOT]']:
        # Do not smack the bots, ever. Also, don't add their messages.
        return
    modes = bot.channels[channel]['modes']
    for mode in modes:
        if modes[mode] == True:  # Skip channel modes. Non-empty list being truthy, we test == True.
            continue
        if sender in modes[mode] and levels[mode] > 2:
            print("Ignored because halfop or higher.")
            return
    msgs = session.query(messagecounter.Messagecounter).filter(messagecounter.Messagecounter.nickname == sender).count()
    print(f"Msgcount: {msgs}")
    # TODO: This should honestly get us the modes for the user, but apparently not?
    # uinfo = await bot.whois(sender)
    # print(f"Userinfo: {uinfo}")

    if msgs > maxmessages:

        await bot.kick(channel, sender, kick_reason)
    msg = messagecounter.Messagecounter(timestamp=datetime.datetime.now(), nickname=sender, hostmask=sender, msg='Placeholder')
    session.add(msg)
    session.commit()

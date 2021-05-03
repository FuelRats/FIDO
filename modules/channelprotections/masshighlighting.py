from typing import List

import fido
from models import config, SessionManager


async def on_message(bot: fido, channel: str, sender: str, message: str):
    session = SessionManager().session
    kick_reason: str = session.query(config.Config).filter_by(module='channelprotection', key='reason')[0].value
    max_highlight_count: int = int(
        session.query(config.Config).filter_by(module='channelprotection', key='maxhighlightcount')[0].value)

    highlighted_users: List[str] = []
    channel_users = [x.lower() for x in bot.channels[channel]['users']]
    for word in message.split(' '):
        word = word.lstrip('@').rstrip(',.:').lower()
        if word in channel_users:
            highlighted_users.append(word)
    if len(highlighted_users) >= max_highlight_count:
        await bot.kick(channel, sender, kick_reason)
        await bot.message("#opers", f"{sender} was kicked from channel {channel} for highlight spam.")
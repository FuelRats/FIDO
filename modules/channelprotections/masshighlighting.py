from typing import List

import fido
from models import config, SessionManager


async def on_message(bot: fido, channel: str, sender: str, message: str):
    session = SessionManager().session
    kick_reason: str = session.query(config.Config).filter_by(module='channelprotection', key='reason')[0].value
    max_highlight_count: int = int(
        session.query(config.Config).filter_by(module='channelprotection', key='maxhighlightcount')[0].value)

    highlighted_users: List[str] = []
    for word in message.split(' '):
        word = word.lstrip('@')
        for user in bot.channels[channel]['users']:
            if word.startswith(user) and user not in highlighted_users:
                print(f"Matched as user: {word}")
                highlighted_users.append(user)
    if len(highlighted_users) >= max_highlight_count:
        await bot.kick(channel, sender, kick_reason)
        await bot.message("#opers", f"{sender} was kicked from channel {channel} for highlight spam.")
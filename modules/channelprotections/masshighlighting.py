from typing import List

import fido


async def on_message(bot: fido, channel: str, sender: str, message: str):
    highlighted_users: List[str] = []
    for word in message.split(' '):
        word = word.lstrip('@')
        for user in bot.channels[channel]['users']:
            if word.startswith(user) and user not in highlighted_users:
                highlighted_users.append(user)
    if len(highlighted_users) > 5:
        await bot.kick(channel, sender, 'fuck off')

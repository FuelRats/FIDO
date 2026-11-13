from typing import List

import fido
from modules import configmanager
from modules.access import channel_state


async def on_message(bot: fido, channel: str, sender: str, message: str):
    state = channel_state(bot, channel, "mass highlight check skipped")
    if state is None:
        return
    kick_reason: str = (configmanager.get_value('channelprotection', 'reason_highlight')
                        or configmanager.get_value('channelprotection', 'reason'))
    max_highlight_count: int = int(configmanager.get_value('channelprotection', 'maxhighlightcount'))

    highlighted_users: List[str] = []
    channel_users = [x.lower() for x in state['users']]
    for word in message.split(' '):
        word = word.lstrip('@').rstrip(',.:').lower()
        if word in channel_users:
            highlighted_users.append(word)
    if len(highlighted_users) >= max_highlight_count:
        await bot.kick(channel, sender, kick_reason)
        await bot.message("#opers", f"{sender} was kicked from channel {channel} for highlight spam.")
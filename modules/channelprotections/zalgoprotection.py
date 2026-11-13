from modules import configmanager
from modules.access import channel_state

import fido
import math
import sys
import unicodedata

ZALGO_CHAR_CATEGORIES = ['Mn', 'Me']
THRESHOLD = 0.5
PERCENTILE = 0.75
# A word counts only if one base character carries at least this many combining marks. Accented
# writing (Vietnamese, French, Polish ...) stacks at most two.
MIN_STACKED_MARKS = 3


def percentile(scores: list):
    if len(scores) == 0:
        return 0
    
    scores = sorted(scores)
    i = len(scores) * PERCENTILE - 0.5
    f = math.floor(i)
    if abs(f - i) < sys.float_info.epsilon:
        return scores[f]
    
    fract = i - f
    return (1 - fract) * scores[f] + fract * scores[min(f + 1, len(scores) - 1)]


def longest_mark_stack(cats: list) -> int:
    """The most combining marks in a row, that is on one base character."""
    longest = run = 0
    for cat in cats:
        run = run + 1 if cat in ZALGO_CHAR_CATEGORIES else 0
        longest = max(longest, run)
    return longest


def is_zalgo(s):
    if len(s) == 0:
        return False
    word_scores = []
    for word in s.split():
        cats = [unicodedata.category(c) for c in word]
        if longest_mark_stack(cats) < MIN_STACKED_MARKS:
            word_scores.append(0)
            continue
        score = sum([cats.count(banned) for banned in ZALGO_CHAR_CATEGORIES]) / len(word)
        word_scores.append(score)
    total_score = percentile(word_scores)
    return total_score > THRESHOLD


async def on_message(bot: fido, channel: str, sender: str, message: str):
    if channel_state(bot, channel, "zalgo check skipped") is None:  # the kick needs the channel
        return
    kick_reason: str = (configmanager.get_value('channelprotection', 'reason_zalgo')
                        or configmanager.get_value('channelprotection', 'reason'))

    if is_zalgo(unicodedata.normalize('NFD', message)):
        await bot.kick(channel, sender, kick_reason)
        await bot.message("#opers", f"{sender} was kicked from channel {channel} for using zalgo.")

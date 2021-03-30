from typing import List
from models import config, SessionManager

import codecs
import fido
import math
import re
import sys
import unicodedata

ZALGO_CHAR_CATEGORIES = ['Mn', 'Me']
THRESHOLD = 0.5
PERCENTILE = 0.75


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


def is_zalgo(s):
    if len(s) == 0:
        return False
    word_scores = []
    for word in s.split():
        cats = [unicodedata.category(c) for c in word]
        score = sum([cats.count(banned) for banned in ZALGO_CHAR_CATEGORIES]) / len(word)
        word_scores.append(score)
    total_score = percentile(word_scores)
    return total_score > THRESHOLD


async def on_message(bot: fido, channel: str, sender: str, message: str):
    session = SessionManager().session
    kick_reason: str = session.query(config.Config).filter_by(module='channelprotection', key='reason')[0].value

    if is_zalgo(unicodedata.normalize('NFD', message)):
        await bot.kick(channel, sender, kick_reason)
        await bot.message("#opers", f"{sender} was kicked from channel {channel} for using zalgo.")

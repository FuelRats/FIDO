import functools
import logging
import time
from enum import Enum
import fido

log = logging.getLogger(__name__)

# Channel prefix modes (UnrealIRCd PREFIX=(qaohv)~&@%+) and their rank. Other channel modes are ignored.
levels = {
    "q": 5,  # q owner
    "a": 4,  # a admin
    "o": 3,  # o op
    "h": 2,  # h half-op
    "v": 1,  # v voice
}

OPER_CACHE_SECONDS = 60  # how long a WHOIS answer about IRC operator status is reused


# TODO: Skip this whole integer shit, just address the modes directly by mode letter in the enum.
# Actually, don't. We need to rank these somehow, after all... Other suggestions?
class Levels(Enum):
    OWNER = 5
    ADMIN = 4
    OP = 3
    HALFOP = 2
    VOICE = 1
    NONE = 0


def get_access_level(bot: fido, channel: str, nick: str) -> Levels:
    """
    Gets the access level of a user
    :param bot: Bot instance
    :param channel: Channel to check permission in
    :param nick: Nick of user
    :return: The user's access level
    """
    modes = bot.channels[channel]['modes']
    maxlevel = Levels.NONE
    for mode, level in levels.items():
        holders = modes.get(mode)
        if isinstance(holders, list) and nick in holders and level > maxlevel.value:
            maxlevel = Levels(level)
            log.debug(f"Maxlevel now {maxlevel}")
    return maxlevel


def require_permission(level: Levels, above: bool = True, message: str = None):
    """
    Requires the invoking user to have a specified privilege level in the channel the command was used in
    :param level: Permission level
    :param above: (optional, default: True) permission above or below required
    :param message: (optional) denial reply, stating the reason
    :return:
    """

    def actual_decorator(function):
        @functools.wraps(function)
        async def guarded(bot: fido, channel: str, nick: str, *args, **kwargs):
            if channel not in bot.channels:
                return None
            log.debug(f"Modes: {bot.channels[channel]['modes']}")
            maxlevel = get_access_level(bot, channel, nick)
            log.debug(f"Required level {level.value} and maxlevel {maxlevel.value}")
            if (above and maxlevel.value < level.value) or (not above and maxlevel.value > level.value):
                if message:
                    await bot.message(channel, message)
            else:
                return await function(bot, channel, nick, *args, **kwargs)

        return guarded

    return actual_decorator


async def is_irc_operator(bot: fido, nick: str) -> bool:
    """
    Whether nick is an IRC operator, from the 313 line of a WHOIS (pydle's 'oper' field). The answer is
    cached per nick for OPER_CACHE_SECONDS; forget_oper drops it on a nick change or quit.
    """
    key = bot.normalize(nick)
    cached = bot.oper_cache.get(key)
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]
    generation = bot.oper_cache_generation
    whois = await bot.whois(nick)
    oper = bool(whois and whois.get('oper'))
    if bot.oper_cache_generation == generation:
        # No nick change or quit happened during the WHOIS, so the answer still belongs to this nick.
        bot.oper_cache[key] = (time.monotonic() + OPER_CACHE_SECONDS, oper)
    return oper


def forget_oper(bot: fido, nick: str):
    """Drop the cached operator status of nick."""
    bot.oper_cache.pop(bot.normalize(nick), None)
    bot.oper_cache_generation += 1


def require_oper(action: str):
    """
    Requires the invoking user to be an IRC operator, for commands with network-wide effects.
    :param action: what the command does, for the denial reply ("You must be an IRC operator to <action>.")
    """

    def actual_decorator(function):
        @functools.wraps(function)
        async def guarded(bot: fido, channel: str, nick: str, *args, **kwargs):
            if channel not in bot.channels:
                return None
            if not await is_irc_operator(bot, nick):
                log.info(f"Denied {function.__module__}.{function.__name__} to {nick}: not an IRC operator")
                await bot.message(channel, f"You must be an IRC operator to {action}.")
                return None
            return await function(bot, channel, nick, *args, **kwargs)

        return guarded

    return actual_decorator

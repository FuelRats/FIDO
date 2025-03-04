import functools
from enum import Enum
import fido

levels = {
    "q": 5,  # q owner
    "a": 4,  # a admin
    "o": 3,  # o op
    "h": 2,  # h half-op
    "v": 1,  # v voice
    None: 0
}


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
    for mode in modes:
        if modes[mode] is True:  # Skip channel modes.
            continue
        if nick in modes[mode] and levels[mode] > maxlevel.value:
            maxlevel = Levels(levels[mode])
            print(f"Maxlevel now {maxlevel}")
    return maxlevel


def require_permission(level: Levels, above: bool = True, message: str = None):
    """
    Requires the invoking user to have a specified privilege level
    :param level: Permission level
    :param above: (optional, default: True) permission above or below required
    :param message: (optional) overwrite message
    :return:
    """

    def actual_decorator(function):
        @functools.wraps(function)
        async def guarded(bot: fido, channel: str, nick: str, *args, **kwargs):
            if channel not in bot.channels:
                return None
            print(f"Modes: {bot.channels[channel]['modes']}")
            maxlevel = get_access_level(bot, channel, nick)
            print(f"Required level {level.value} and maxlevel {maxlevel.value}")
            if (above and maxlevel.value < level.value) or (not above and maxlevel.value > level.value):
                if message:
                    await bot.message(channel, message)
                    pass
            else:
                return await function(bot, channel, nick, *args, **kwargs)

        return guarded

    return actual_decorator

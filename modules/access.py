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
            modes = bot.channels[channel]['modes']
            maxlevel: Levels = Levels.NONE
            for mode in modes:
                if modes[mode] == True:  # Skip channel modes. Non-empty list being truthy, we test == True.
                    continue
                if nick in modes[mode] and levels[mode] > maxlevel.value:
                    maxlevel = Levels(levels[mode])
                    print(f"Maxlevel now {maxlevel}")
            print(f"Required level {level.value} and maxlevel {maxlevel.value}")
            if (above and maxlevel.value < level.value) or (not above and maxlevel.value > level.value):
                if message:
                    await bot.message(channel, message)
                    pass
            else:
                return await function(bot, channel, nick, *args, **kwargs)

        return guarded

    return actual_decorator

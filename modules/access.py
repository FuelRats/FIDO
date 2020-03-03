import functools

import fido

levels = {
    "q": 5,  # q owner
    "a": 4,  # a admin
    "o": 3,  # o op
    "h": 2,  # h half-op
    "v": 1,  # v voice
    None: 0
}


def require_permission(level: int, above: bool = True, message: str = None):
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
            maxlevel: int = 0
            for mode in modes:
                if modes[mode] == True:
                    continue
                print(f"Mode: {mode} Nick: {nick}")
                if nick in modes[mode] and levels[mode] > maxlevel:
                    maxlevel = levels[mode]

            if above and maxlevel <= level or not above and maxlevel >= level:
                if message:
                    await bot.message(channel, message)
                    pass
            else:
                return await function(bot, channel, nick, *args, **kwargs)

        return guarded

    return actual_decorator

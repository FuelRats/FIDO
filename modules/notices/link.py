import fido
from modules import configmanager

RATCHAT = '#ratchat'


async def on_unreliable(bot: fido, message: str, match):
    """
    Handler for link.LINK_UNRELIABLE: warn the oper channel and, behind its own gate, #ratchat.
    :param bot: bot instance
    :param message: notice text after the frame
    :param match: match of patterns.PATTERNS['link.LINK_UNRELIABLE']
    """
    server = match.group('server')
    seconds = match.group('seconds')
    if configmanager.gate_open(configmanager.GATE_OPERS_REPORTS):
        await bot.message(
            bot.get_oper_channel(),
            f"{bot.colour_yellow('LINK WARNING')} Connection to {server} is unstable (no response for {seconds} seconds)."
        )
    if configmanager.gate_open(configmanager.GATE_RATCHAT_LINK_WARNINGS):
        await bot.message(
            RATCHAT,
            f"{bot.colour_yellow('LINK WARNING')} Connection to {server} is unstable (no response for {seconds} seconds). A netsplit may occur soon."
        )


async def on_disconnected(bot: fido, message: str, match):
    """
    Handler for link.LINK_DISCONNECTED: report the lost link to the oper channel.
    :param bot: bot instance
    :param message: notice text after the frame
    :param match: match of patterns.PATTERNS['link.LINK_DISCONNECTED']
    """
    if not configmanager.gate_open(configmanager.GATE_OPERS_REPORTS):
        return
    server = match.group('server')
    await bot.message(
        bot.get_oper_channel(),
        f"{bot.colour_red('LINK DOWN')} Lost server link to {server}."
    )


async def on_linked(bot: fido, message: str, match):
    """
    Handler for link.SERVER_LINKED: report the restored link to the oper channel.
    :param bot: bot instance
    :param message: notice text after the frame
    :param match: match of patterns.PATTERNS['link.SERVER_LINKED']
    """
    if not configmanager.gate_open(configmanager.GATE_OPERS_REPORTS):
        return
    from_server = match.group('src')
    to_server = match.group('dst')
    await bot.message(
        bot.get_oper_channel(),
        f"{bot.colour_green('LINK RESTORED')} Server link reestablished: {from_server} -> {to_server}"
    )

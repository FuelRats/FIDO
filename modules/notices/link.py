import re
import fido

regex_unreliable = re.compile(
    r'.*link\.LINK_UNRELIABLE \[warn\] Warning, no response from (?P<server>[A-Za-z0-9.\-]+) for (?P<seconds>\d+) seconds',
    re.I
)

regex_disconnected = re.compile(
    r'.*link\.LINK_DISCONNECTED \[error\] Lost server link to (?P<server>[A-Za-z0-9.\-]+) \[(?P<ip>[0-9a-fA-F:]+)\]: (?P<reason>.+)',
    re.I
)

regex_linked = re.compile(
    r'.*link\.SERVER_LINKED \[info\] Server linked: (?P<from>[A-Za-z0-9.\-]+) -> (?P<to>[A-Za-z0-9.\-]+) \[secure: (?P<tls>[^\]]+)\]',
    re.I
)

async def on_unreliable(bot: fido, message: str, match):
    operchannel = bot.get_oper_channel()
    server = match.group('server')
    seconds = match.group('seconds')
    await bot.message(
        operchannel,
        f"{bot.colour_yellow('LINK WARNING')} Connection to {server} is unstable (no response for {seconds} seconds)."
    )
    await bot.message(
        "#ratchat",
        f"{bot.colour_yellow('LINK WARNING')} Connection to {server} is unstable (no response for {seconds} seconds). A netsplit may occur soon."
    )

async def on_disconnected(bot: fido, message: str, match):
    operchannel = bot.get_oper_channel()
    server = match.group('server')
    ip = match.group('ip')
    reason = match.group('reason')
    await bot.message(
        operchannel,
        f"{bot.colour_red('LINK DOWN')} Lost server link to {server}."
    )

async def on_linked(bot: fido, message: str, match):
    operchannel = bot.get_oper_channel()
    from_server = match.group('from')
    to_server = match.group('to')
    tls = match.group('tls')
    await bot.message(
        operchannel,
        f"{bot.colour_green('LINK RESTORED')} Server link reestablished: {from_server} -> {to_server}"
    )
from typing import List
from config import IRC
import cryptocompare
import yfinance
import fido
import json

from modules.access import require_permission, Levels
import logging

log = logging.getLogger(__name__)


async def crypto_compare(bot: fido, channel: str, sender: str, args: List[str]):

    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "compare <crypto currency> [Fiat currency] (default USD)"
    if channel not in ['#stonks']:
        await bot.message(channel, "This command can only be used in certain channels.")
        return
    if len(args) == 1:
        price = cryptocompare.get_price(args[0], 'USD')[args[0]]['USD']
        if price:
            await bot.message(channel, f"{args[0].upper()} is currently trading at {price} USD")
        else:
            await bot.message(channel, f"Unknown currency {args[0]}")
    elif len(args) == 2:
        price = cryptocompare.get_price(args[0], args[1])[args[0]][args[1]]
        if price:
            await bot.message(channel, f"{args[0].upper()} is currently trading at {price} {args[1].upper()}")
    else:
        await bot.message(channel, "Please provide only 1 or 2 arguments, the first "
                                   "being the crypto and the optional second another currency.")
    return


async def crypto_value(bot: fido, channel: str, sender: str, args: List[str]):

    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "value <amount> <crypto currency> [Fiat currency] (default USD)"
    if channel not in ['#stonks']:
        await bot.message(channel, "This command can only be used in certain channels.")
        return
    if len(args) == 2:
        price = cryptocompare.get_price(args[1], 'USD')[args[1]]['USD']
        if price:
            value = price * float(args[0])
            await bot.message(channel, f"{args[0]} {args[1].upper()} is currently worth ${value} USD")
        else:
            await bot.message(channel, f"Unknown currency {args[1]}")
    elif len(args) == 3:
        price = cryptocompare.get_price(args[1], args[2])[args[1]][args[2]]
        if price:
            value = price * float(args[0])
            await bot.message(channel, f"{args[0]} {args[1].upper()} is currently worth ${value} {args[1].upper()}")
    else:
        await bot.message(channel, "Please provide only 2 or 3 arguments, the first "
                                   "being the value, the second the crypto and the optional third another currency.")
    return


async def ticker_info(bot: fido, channel: str, sender: str, args: List[str]):
    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "value <amount> <crypto currency> [Fiat currency] (default USD)"
    if channel not in ['#stonks']:
        await bot.message(channel, "This command can only be used in certain channels.")
        return
    stonk = yfinance.Ticker(args[0])
    if stonk:
        await bot.message(channel, f"{stonk.info['shortName']}: Close: {stonk.info['previousClose']} "
                                   f"Open: {stonk.info['regularMarketOpen']} "
                                   f"High: {stonk.info['regularMarketDayHigh']} "
                                   f"Low: {stonk.info['regularMarketDayLow']} "
                                   f"Volume: {stonk.info['regularMarketVolume']} "
                                   f"Current: {stonk.info['bid']}B/{stonk.info['ask']}A")
    return

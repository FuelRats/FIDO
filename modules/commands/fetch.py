from typing import List
from config import IRC
import requests
import ipaddress
import fido
from modules.access import require_permission


@require_permission(level=4, message='DENIED!')
async def invoke(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !fetch command
    :param sender: Sender of the IRC command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """

    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "fetch <ip adress1> [<ip address2> <ip address3> ...]"

    lines = []
    for arg in args:
        try:
            ipaddress.ip_address(arg)
        except ValueError:
            return arg + " is an invalid IP Address"

        response = requests.get('https://ipinfo.io/' + arg, headers={'Accept': 'application/json'}).json()
        location = []
        if 'city' in response and response['city'] != '':
            location.append(response['city'])
        if 'region' in response and response['region'] != '':
            location.append(response['region'])
        if 'country' in response:
            country = response['country']
            flag = chr(ord(country[0]) + 127397) + chr(ord(country[1]) + 127397)
            location.append(f"{flag} ({country})")
        if len(location) == 0:
            location.append("Unknown Location")
        location = ", ".join(location)
        lines.append(f"IP Information {response['ip']}: {location} ISP: {response['org'] if 'org' in response else 'Unknown'}" +
                     (f" Hostname: {response['hostname']}" if 'hostname' in response else ""))

    answer = "\r\n".join(lines)
    await bot.message(channel, answer)

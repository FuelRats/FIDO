from typing import List
from config import IRC
import requests
import ipaddress
import fido


async def invoke(bot: fido, args: List[str]):
    """
    Handler for the !fetch command
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
        if response['city'] != '':
            location.append(response['city'])
        if response['region'] != '':
            location.append(response['region'])
        country = response['country']
        flag = chr(ord(country[0]) + 127397) + chr(ord(country[1]) + 127397)
        location.append(f"{flag} ({country})")
        location = ", ".join(location)
        lines.append(f"IP Information {response['ip']}: {location} ISP: {response['org']}" +
                     (f" Hostname: {response['hostname']}" if 'hostname' in response else ""))

    answer = "\r\n".join(lines)
    return answer

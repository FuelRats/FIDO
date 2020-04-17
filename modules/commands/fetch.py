from typing import List
from config import IRC
import requests
import ipaddress
import fido
from requests.exceptions import SSLError
from OpenSSL.SSL import Error

from modules.access import require_permission, Levels


@require_permission(level=Levels.OP, message='DENIED!')
async def invoke(bot: fido, channel: str, sender: str, args: List[str]):
    """
    Handler for the !fetch command
    :param channel: Channel the command is invoked in
    :param sender: Sender of the IRC command
    :param bot: bot instance
    :param args: Arguments passed to the command by the user
    :return: The reply message
    """

    if len(args) == 0:
        return "Usage: " + IRC.commandPrefix + "fetch <ip adress1> [<ip address2> <ip address3> ...]"

    lines = []
    for arg in args:
        ip = ""
        if arg in bot.users:
            # TODO: Pydle does not currently support fetching real hostnames/ips, only cloaks/vhosts
            # whois = await bot.whois(arg)
            # ip = bot.users[arg]['hostname']
            lines.append("Nicknames can't currently be looked up, please supply an IP instead.")
            continue
        else:
            try:
                ipaddress.ip_address(arg)
                ip = arg
            except ValueError:
                return arg + " is an invalid IP Address"
        try:
            response = requests.get(f'https://ipinfo.io/{ip}', headers={'Accept': 'application/json'}).json()
        except SSLError:
            await bot.message(channel, "An SSL error occurred while trying to retrieve IP information.")
            return
        print(response)
        location = []
        if 'error' in response:
            lines.append(f"Could not fetch IP information for {ip}: {response['error']['title']}: {response['error']['message']}")
            continue
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

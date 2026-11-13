import datetime
import ipaddress
import logging
import fido
from models import drones, session_scope
from modules import access, configmanager
import re

log = logging.getLogger(__name__)

# A proxy monitor's report; it starts the message.
regex = re.compile(
    r'DNSBL -> (?P<nick>.*)!(?P<user>.*)@[A-Za-z0-9.:_\-]* \[(?P<ip>[A-Za-z0-9.:_\-]*)\] appears '
    r'in BL zone (?P<zone>[A-Za-z0-9.:_\-]*) \((?P<type>.*)\)')

# Lockdown: unidentified users joining #ratchat are forwarded to #NewRats. The named form is what
# UnrealIRCd stores and lists, so the -b of !unlock matches it.
LOCKDOWN_CHANNEL = '#ratchat'
LOCKDOWN_BAN = '~forward:#NewRats:~security-group:unknown-users'
LOCKDOWN_STATE = ('droneprotection', 'lockdown')  # a row holding "True" while a lockdown is on
LOCKDOWN_ON = 'True'


def in_lockdown() -> bool:
    """A lockdown is on while its row holds "True"; a missing row means off."""
    return configmanager.get_value(*LOCKDOWN_STATE) == LOCKDOWN_ON


async def on_message(bot: fido, channel: str, sender: str, message: str):
    # Locks down if an excessive number of drones start joining the network. We're only interested in msgs in
    # the #opers channel, from IRC operators.
    if channel != '#opers':
        return
    # Only act if we're seeing a DNSBl message.
    if 'DNSBL' not in message:
        return
    maxdrones: int = int(configmanager.get_value('channelprotection', 'maxdrones'))
    retention_time: int = int(configmanager.get_value('channelprotection', 'droneinterval'))

    # Clear out old drones
    delta = datetime.datetime.now() - datetime.timedelta(minutes=retention_time)
    with session_scope() as session:
        session.query(drones.Drones).filter(drones.Drones.timestamp <= delta).delete()
    match = re.match(regex, message)
    if match:
        if not await access.is_irc_operator(bot, sender):
            log.info(f"Ignored a DNSBL report from {sender}: not an IRC operator")
            return
        try:
            ipaddress.ip_address(match.group('ip'))
        except ValueError:
            log.warning(f"Ignored a DNSBL report from {sender}: its address is not an IP address")
            return
        log.info(f"Got a regex match for DNSBL message: {match.group('nick')} is a "
                 f"{match.group('type')} listed in {match.group('zone')}")
        drone = drones.Drones(timestamp=datetime.datetime.now(), nickname=match.group('nick'),
                              hostmask=match.group('ip'), msg=f"{match.group('zone')}: {match.group('type')}")
        with session_scope() as session:
            session.add(drone)
        locked_down = in_lockdown()
        with session_scope() as session:
            dronecount = session.query(drones.Drones).count()
        log.debug(f"Lockdown status: {locked_down}.")
        if not configmanager.gate_open(configmanager.GATE_AUTO_LOCKDOWN):
            log.info("Automatic lockdown and G-lines are off (channelprotection/auto_lockdown)")
        elif locked_down:
            # We're already in lockdown, just slaughter.
            log.info(f"Lockdown G-Line of {match.group('nick')}.")
            await bot.message("#opers", f"LOCKDOWN: Automatically GLINEd {match.group('nick')} (DNSBL)")
            await bot.raw(f"GLINE *@{match.group('ip')} 7d Connecting through a VPN or open proxy is not "
                             f"currently allowed.\n")
        else:
            # Should we go to lockdown due to number of drones?
            if dronecount > maxdrones:
                log.warning("LOCKDOWN!")
                await bot.message("#opers", f"*** LOCKDOWN INITIATED *** More than {maxdrones} Drones connected in "
                                            f"the past {retention_time} minutes. "
                                            "I am now G-Lining all new drone connections.")
                await bot.message(LOCKDOWN_CHANNEL, "*** LOCKDOWN INITIATED *** Excessive drones connecting to "
                                                    "network, new connections failing drone scans will now be "
                                                    "G-Lined. This may cause clients to not be able to connect.")
                await bot.rawmsg('MODE', LOCKDOWN_CHANNEL, '+b', LOCKDOWN_BAN)
                await bot.rawmsg('MODE', '#NewRats', '-i')
                configmanager.set_config(*LOCKDOWN_STATE, LOCKDOWN_ON)
        if "Compromised router" in match.group('zone'):
            await bot.message("#ratchat", f"Advisory: Client {match.group('nick')}'s IP address is listed in a "
                                          f"blacklist indicating their router / gateway hosts malware. "
                                          f"Inform client during debrief.")
    else:
        log.warning("*** No RE match even though DNSBL...")

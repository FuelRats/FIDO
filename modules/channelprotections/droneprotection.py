import datetime
import fido
from models import config, SessionManager, drones
from modules import configmanager
import re

regex = re.compile(
    '.*DNSBL -> (?P<nick>.*)!(?P<user>.*)@[A-Za-z0-9.:_\-]* \[(?P<ip>[A-Za-z0-9.:_\-]*)\] appears '
    'in BL zone (?P<zone>[A-Za-z0-9.:_\-]*) \((?P<type>.*)\)')

levels = {
    "q": 5,  # q owner
    "a": 4,  # a admin
    "o": 3,  # o op
    "h": 2,  # h half-op
    "v": 1,  # v voice
    None: 0
}


async def on_message(bot: fido, channel: str, sender: str, message: str):
    # Locks down if an excessive number of drones start joining the network. We're only interested in msgs in
    # the #opers channel.
    if channel != '#opers':
        return
    # Only act if we're seeing a DNSBl message.
    if 'DNSBL' not in message:
        return
    session = SessionManager().session
    maxdrones: int = int(
        session.query(config.Config).filter_by(module='channelprotection', key='maxdrones')[0].value)
    retention_time: int = int(
        session.query(config.Config).filter_by(module='channelprotection', key='droneinterval')[0].value)

    # Clear out old drones
    delta = datetime.datetime.now() - datetime.timedelta(minutes=retention_time)
    session.query(drones.Drones).filter(drones.Drones.timestamp <= delta).delete()
    session.commit()
    match = re.match(regex, message)
    if match:
        print(f"Got a regex match for DNSBL message: {match.group('nick')} is a "
              f"{match.group('type')} listed in {match.group('zone')}")
        drone = drones.Drones(timestamp=datetime.datetime.now(), nickname=match.group('nick'),
                              hostmask=match.group('ip'), msg=f"{match.group('zone')}: {match.group('type')}")
        session.add(drone)
        session.commit()
        lockdown = configmanager.get_config('droneprotection', 'lockdown')
        dronecount = session.query(drones.Drones).count()
        print(f"Lockdown status: {lockdown[0]}.")
        if lockdown[0] == "True":
            # We're already in lockdown, just slaughter.
            print(f"Theoretical KILL of {match.group('nick')}.")
            await bot.raw(f"KILL {match.group('nick')} Connecting through a VPN or open proxy is not "
                             f"currently allowed.")
            await bot.message("#opers", f"LOCKDOWN: Automatically killed {match.group('nick')} (DNSBL)")
        else:
            # Should we go to lockdown due to number of drones?
            if dronecount > maxdrones:
                print("LOCKDOWN!")
                await bot.message("#opers", f"*** LOCKDOWN INITIATED *** More than {maxdrones} Drones connected in "
                                            f"the past {retention_time} minutes. "
                                            f"I am now KILLing all new drone connections.")
                await bot.message("#ratchat", f"*** LOCKDOWN INITIATED *** Excessive drones connecting to network, "
                                              f"new connections failing drone scans will now be KILLed. This may cause "
                                              f"clients to not be able to connect.")
                configmanager.set_config('droneprotection', 'lockdown', "True")
        if "Compromised router" in match.group('zone'):
            await bot.message("#ratchat", f"Advisory: Client {match.group('nick')}'s IP address is listed in a "
                                          f"blacklist indicating their router / gateway hosts malware. "
                                          f"Inform client during debrief.")
    else:
        print("*** No RE match even though DNSBL...")

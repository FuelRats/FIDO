import sys

import pydle
import time, requests, threading
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import IRC, Logging, SQLAlchemy
from models import SessionManager, config, monitor
from models.config import Config
from modules import noticehandler, channelprotectionhandler
from modules import commandhandler as commandHandler
from modules import sessiontracker
from modules import configmanager
from modules import nexmo
from modules.newrats import induction

pool = pydle.ClientPool()

logging.basicConfig(stream=sys.stdout, level=Logging.level)

#baseClient = pydle.featurize(pydle.features.CTCPSupport, pydle.features.AccountSupport,
#                             pydle.features.IRCv3Support, pydle.features.WHOXSupport, pydle.features.ISUPPORTSupport,
#                             pydle.features.TLSSupport, pydle.features.ircv3.CapabilityNegotiationSupport,
#                             pydle.features.ircv3.SASLSupport, pydle.features.ircv3.MonitoringSupport,
#                             pydle.features.ircv3.TaggedMessageSupport, pydle.features.ircv3.MetadataSupport,
#                             pydle.features.rfc1459.RFC1459Support)


class FIDO(pydle.Client):
    operchannel: str = None

    def __init__(self, *args, **kwargs):
        self.recent_greeting = []
        super().__init__(*args, **kwargs)

    @pydle.coroutine
    async def on_connect(self):
        await super().on_connect()
        logging.info("Connected!")
        await self.raw(f"OPER {IRC.operline} {IRC.operlinePassword}\r\n")  # DO NOT REMOVE NEWLINE!!!!!!!
        print(configmanager.get_config(module="channels", key="join"))
        # Join remembered channels
        for channel in configmanager.get_config(module='channels', key='join'):
            await self.join(channel)
        # TODO: Seed session cache by reading /who output on join?
        sessionmanager = SessionManager()
        session = sessionmanager.session
        monitors = session.query(monitor.Monitor).all()
        for mon in monitors:
            self.monitor(mon.nickname)

    @pydle.coroutine
    async def on_join(self, channel, user):
        await super().on_join(channel, user)
        await induction.on_join(self, channel, user)
        # TODO: Maybe session cache here instead?

    @pydle.coroutine
    async def on_raw(self, message):
        await super().on_raw(message)

    @pydle.coroutine
    async def on_channel_message(self, target, nick, message):
        await super().on_channel_message(target, nick, message)
        await channelprotectionhandler.handle_message(self, target, nick, message)
        await commandHandler.on_channel_message(self, target, nick, message)

    @pydle.coroutine
    async def on_channel_notice(self, target, nick, message):
        await super().on_channel_notice(target, nick, message)

    @pydle.coroutine
    async def on_ctcp(self, by, target, what, contents):
        await super().on_ctcp(by, target, what, contents)
        if what == 'ACTION':
            await channelprotectionhandler.handle_message(self, target, by, contents)

    @pydle.coroutine
    async def on_private_message(self, target, nick, message):
        await super().on_private_message(target, nick, message)
        await commandHandler.on_private_message(self, nick, message)

    @pydle.coroutine
    async def on_notice(self, target, nick, message):
        await super().on_notice(target, nick, message)
        logging.debug(f"target: {target}, nick: {nick}, message: {message}")
        await noticehandler.handle_notice(self, message)

    @pydle.coroutine
    async def on_user_online(self, nickname):
        await super().on_user_online(nickname)
        logging.debug(f"Monitored user {nickname} is online.")
        await self.message("#rat-ops", f"Monitored user {nickname} is online!")

    @pydle.coroutine
    async def on_user_offline(self, nickname):
        await super().on_user_offline(nickname)
        logging.debug(f"Monitored user {nickname} is now offline.")
        await self.message("#rat-ops", f"Monitored user {nickname} is now offline.")

    @staticmethod
    def colour_red(message: str):
        return f"\u000304{message}\u000f"

    def get_oper_channel(self):
        if self.operchannel is None:
            session = SessionManager().session
            self.operchannel = session.query(config.Config).filter_by(module='channels', key='operchannel')[0].value
        return self.operchannel


if __name__ == '__main__':
    client = FIDO(IRC.nickname)
    pool.connect(client, IRC.server, IRC.port, tls=IRC.useSsl)
    thread = threading.Thread(target=pool.handle_forever)
    thread.start()

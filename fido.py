import sys

import pydle
import time, requests, threading
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import IRC, Logging, SQLAlchemy
from models import SessionManager, config
from models.config import Config
from modules import noticehandler, channelprotectionhandler
from modules import commandhandler as commandHandler
from modules import sessiontracker

pool = pydle.ClientPool()

logging.basicConfig(stream=sys.stdout, level=Logging.level)


class FIDO(pydle.Client):
    operchannel: str = None

    @pydle.coroutine
    async def on_connect(self):
        await super().on_connect()
        logging.info("Connected!")
        await self.raw(f"OPER {IRC.operline} {IRC.operlinePassword}\r\n")  # DO NOT REMOVE NEWLINE!!!!!!!

        # Join remembered channels
        session = SessionManager().session
        for result in session.query(config.Config).filter_by(module='channels', key='join'):
            await self.join(result.value)
        # TODO: Seed session cache by reading /who output on join?

    @pydle.coroutine
    async def on_join(self, channel, user):
        await super().on_join(channel, user)
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
    async def on_private_message(self, target, nick, message):
        await super().on_private_message(self, target, nick, message)
        await commandHandler.on_private_message(self, nick, message)

    @pydle.coroutine
    async def on_notice(self, target, nick, message):
        await super().on_notice(target, nick, message)
        logging.debug(f"target: {target}, nick: {nick}, message: {message}")
        await noticehandler.handle_notice(self, message)

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

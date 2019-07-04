import sys

import pydle
import time, requests, threading
import sqlalchemy
import modules.commandhandler as commandHandler
import logging

from config import IRC, Logging
from modules import noticehandler

pool = pydle.ClientPool()

logging.basicConfig(stream=sys.stdout, level=Logging.level)

class FIDO(pydle.Client):

    @pydle.coroutine
    async def on_connect(self):
        logging.debug("test?")
        await super().on_connect()
        logging.info("Connected!")
        await self.raw(f"OPER {IRC.operline} {IRC.operlinePassword}\r\n")  # DO NOT REMOVE NEWLINE!!!!!!!
        await self.join(IRC.channel)

    @pydle.coroutine
    async def on_join(self, channel, user):
        await super().on_join(channel, user)

    @pydle.coroutine
    async def on_raw(self, message):
        await super().on_raw(message)

    @pydle.coroutine
    async def on_message(self, target, nick, message):
        await super().on_message(target, nick, message)
        logging.debug(f"got message: {message} from {nick} with target {target}")
        # print("assuming my username is", self.nickname)
        reply = await commandHandler.handle_command(self, message)
        if reply:
            await self.message(target if target != self.nickname else nick, reply)
        return

    @pydle.coroutine
    async def on_notice(self, target, nick, message):
        await super().on_notice(target, nick, message)
        logging.debug(f"target: {target}, nick: {nick}, message: {message}")
        await noticehandler.handle_notice(self, message)
        return


if __name__ == '__main__':
    client = FIDO(IRC.nickname)
    pool.connect(client, IRC.server, IRC.port, tls=IRC.useSsl)
    thread = threading.Thread(target=pool.handle_forever)
    thread.start()

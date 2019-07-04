import sys

import pydle
import time, requests, threading
import sqlalchemy
import modules.commandhandler as commandHandler
import logging

from config import IRC, Logging

pool = pydle.ClientPool()

logging.basicConfig(stream=sys.stdout, level=Logging.level)

class FIDO(pydle.Client):

    @pydle.coroutine
    async def on_connect(self):
        logging.debug("test?")
        await super().on_connect()
        logging.info("Connected!")
        await self.join(IRC.channel)

    @pydle.coroutine
    async def on_join(self, channel, user):
        await super().on_join(channel, user)

    @pydle.coroutine
    async def on_raw(self, message):
        await super().on_raw(message)
        logging.debug(message)

    @pydle.coroutine
    async def on_message(self, target, nick, message):
        await super().on_message(target, nick, message)
        logging.debug(f"got message: {message} from {nick} with target {target}")
        # print("assuming my username is", self.nickname)
        reply = await commandHandler.handle_command(self, message)
        if reply:
            await self.message(target if target != self.nickname else nick, reply)
        return


if __name__ == '__main__':
    client = FIDO(IRC.nickname)
    pool.connect(client, IRC.server, IRC.port, tls=IRC.useSsl)
    thread = threading.Thread(target=pool.handle_forever)
    thread.start()

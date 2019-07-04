import pydle
import time, requests, threading
import sqlalchemy
import modules.commandHandler as commandHandler

from config import IRC

pool = pydle.ClientPool()


class FIDO(pydle.Client):

    @pydle.coroutine
    async def on_connect(self):
        print("test?")
        await super().on_connect()
        print("Connected!")
        await self.join(IRC.channel)

    @pydle.coroutine
    async def on_join(self, channel, user):
        await super().on_join(channel, user)

    @pydle.coroutine
    async def on_raw(self, message):
        await super().on_raw(message)
        print(message)

    @pydle.coroutine
    async def on_message(self, target, nick, message):
        await super().on_message(target, nick, message)
        print("got message:", message, "from", nick, "with target", target)
        # print("assuming my username is", self.nickname)
        reply = commandHandler.handleCommand(message)
        if reply:
            await self.message(target if target != self.nickname else nick, reply)
        return


if __name__ == '__main__':
    client = FIDO(IRC.nickname)
    pool.connect(client, IRC.server, IRC.port, tls=IRC.useSsl)
    thread = threading.Thread(target=pool.handle_forever)
    thread.start()

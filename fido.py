import pydle
import time, requests, threading
import sqlalchemy

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


if __name__ == '__main__':
    client = FIDO(IRC.nickname)
    pool.connect(client, IRC.server, IRC.port, tls=IRC.useSsl)
    thread = threading.Thread(target=pool.handle_forever)
    thread.start()

import pydle
import time, request
from config import IRC


class FIDO(pydle.Client):

    def on_connect(self):
        super().on_connect()
        print("Connected!")
        self.join(IRC.channel)

    def on_join(self, channel, user):
        super().on_join(channel, user)

    @pydle.coroutine
    def on_raw(self, message):
        super().on_raw(message)


if __name__ == '__main__':
    client = FIDO(IRC.nickname)
    client.connect(IRC.server)
    client.handle_forever()

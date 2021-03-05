import fido
from modules.channelprotections import masshighlighting, spamprotection, droneprotection, zalgoprotection

protections = [masshighlighting.on_message, spamprotection.on_message, droneprotection.on_message, zalgoprotection.on_message]


async def handle_message(bot: fido, channel: str, sender:str, message: str):
    """
    General Channel Protection Handler
    :param bot: bot instance
    :param channel: The channel the message was in
    :param message: The Message received
    :return: the reply to be sent to the sender
    """
    for protection in protections:
        await protection(bot, channel, sender, message)

import fido

from models import SessionManager
from models import ircsessions


async def notify_connect(bot: fido, message: str):
    """
    Handle connection notifications and store sessions.
    :param bot: bot instance
    :param message: Connection notification
    :return: Nothing
    """

    sessionmanager = SessionManager()
    session = sessionmanager.session
    client = ircsessions.IRCSessions(nickname='Foo', hostmask='Bar')

    session.add(client)
    session.commit()

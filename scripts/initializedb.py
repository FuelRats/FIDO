from sqlalchemy import create_engine
from models.meta import Base
from config import SQLAlchemy

from models import ircsessions, config, SessionManager

engine = create_engine(SQLAlchemy.url, echo=True)

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

session = SessionManager().session

# Default config values for now
session.add(config.Config(module='channels', key='operchannel', value='#opers'))
session.add(config.Config(module='channelprotection', key='maxhighlightcount', value='5'))
session.add(config.Config(module='channelprotection', key='reason',
                          value='You must not attempt to disrupt the IRC servers, services or the'
                                ' servers they run on, including but not limited to DDoS attacks, '
                                'attempts to gain privileges, flooding or otherwise interfering '
                                'with the service(s).'))

session.commit()

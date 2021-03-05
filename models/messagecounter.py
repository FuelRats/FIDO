from sqlalchemy import Index, Column, Integer, String, DateTime
from .meta import Base


class Messagecounter(Base):
    __tablename__ = 'messagecounter'
    id = Column(Integer, primary_key=True)  # Auto increment is default on primary key.
    timestamp = Column(DateTime)
    nickname = Column(String)
    hostmask = Column(String)
    msg = Column(String)


Index('messagecounter_idx', Messagecounter.id, unique=True)

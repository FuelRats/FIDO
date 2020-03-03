from sqlalchemy import Index, Column, Integer, String, DateTime
from .meta import Base


class IRCSessions(Base):
    __tablename__ = 'ircsessions'
    id = Column(Integer, primary_key=True)  # Auto increment is default on primary key.
    timestamp = Column(DateTime)
    nickname = Column(String)
    hostmask = Column(String)
    network = Column(String)


Index('ircsessions_idx', IRCSessions.id, unique=True)

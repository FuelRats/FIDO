from sqlalchemy import Index, Column, Integer, String, DateTime
from .meta import Base


class Monitor(Base):
    __tablename__ = 'monitor'
    id = Column(Integer, primary_key=True)  # Auto increment is default on primary key.
    timestamp = Column(DateTime)
    nickname = Column(String)
    msg = Column(String)


Index('monitor_idx', Monitor.id, unique=True)

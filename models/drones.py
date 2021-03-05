from sqlalchemy import Index, Column, Integer, String, DateTime
from .meta import Base


class Drones(Base):
    __tablename__ = 'drones'
    id = Column(Integer, primary_key=True)  # Auto increment is default on primary key.
    timestamp = Column(DateTime)
    nickname = Column(String)
    hostmask = Column(String)
    msg = Column(String)


Index('drones_idx', Drones.id, unique=True)

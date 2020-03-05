from sqlalchemy import Index, Column, Integer, String
from .meta import Base


class Groups(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True)  # Auto increment is default on primary key.
    group = Column(String)
    nickname = Column(String)
    number = Column(String)


Index('groups_idx', Groups.id, unique=True)

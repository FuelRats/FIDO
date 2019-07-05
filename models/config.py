from sqlalchemy import Index, Column, Integer, String
from .meta import Base


class Config(Base):
    __tablename__ = 'config'
    id = Column(Integer, primary_key=True, auto_increment=True)
    module = Column(String)
    key = Column(String)
    value = Column(String)


Index('config_idx', Config.id, unique=True)

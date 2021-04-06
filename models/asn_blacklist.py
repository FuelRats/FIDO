from sqlalchemy import Index, Column, Integer, String, DateTime
from .meta import Base


class ASNBlacklist(Base):
    __tablename__ = 'asn_blacklist'
    id = Column(Integer, primary_key=True)  # Auto increment is default on primary key.
    timestamp = Column(DateTime)
    asn = Column(String)
    prefix = Column(String)
    cidr = Column(String)
    reason = Column(String)
    asn_name = Column(String)


Index('asn_blacklist_idx', ASNBlacklist.id, unique=True)

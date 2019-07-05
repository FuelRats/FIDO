from sqlalchemy import create_engine
from models.meta import Base
from config import SQLAlchemy

from models import ircsessions, config

engine = create_engine(SQLAlchemy.url, echo=True)

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)


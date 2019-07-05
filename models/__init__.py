from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.orm import configure_mappers

from config import SQLAlchemy

configure_mappers()
engine = create_engine(SQLAlchemy.url, echo=True)

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)


class SessionManager(object):
    def __init__(self):
        self.session = Session

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import configure_mappers

from config import SQLAlchemy

configure_mappers()
engine = create_engine(SQLAlchemy.url, echo=False)

# Objects stay readable after their session closes: callers use rows after the scope ends.
Session = sessionmaker(bind=engine, expire_on_commit=False)


def use_engine(new_engine):
    """Bind every session opened from now on to new_engine (tests point this at a temp DB)."""
    global engine
    engine = new_engine
    Session.configure(bind=new_engine)


@contextmanager
def session_scope():
    """
    One session per handler call: committed when the block ends, rolled back if it raises.
    Do not await inside the block: a flushed write would hold the SQLite lock across the await.
    """
    session = Session()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()

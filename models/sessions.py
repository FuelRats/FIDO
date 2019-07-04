from sqlalchemy import Table, Column, Integer, String, MetaData, DateTime
meta = MetaData()

sessions = Table(
    'sessions', meta,
    Column('id', Integer, primary_key=True),
    Column('datetime', DateTime),
    Column('nickname', String),
    Column('hostmask', String),
)

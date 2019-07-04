from sqlalchemy import Table, Column, Integer, String, MetaData, DateTime
meta = MetaData()

sessions = Table(
    'students', meta,
    Column('id', Integer, primary_key = True),
    Column(DateTime),
    Column('nickname', String),
    Column('hostmask', String),
)
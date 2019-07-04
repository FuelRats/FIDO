from sqlalchemy import Table, Column, Integer, String, MetaData
meta = MetaData()

config = Table(
    'config', meta,
    Column('id', Integer, primary_key=True),
    Column('module', String),
    Column('key', String),
    Column('value', String),
)

from sqlalchemy import create_engine, MetaData
from ..models import *

engine = create_engine('sqlite:///fido.db', echo=True)
meta = MetaData()
meta.create_all(engine)

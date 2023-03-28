import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

DB_URI = os.environ.get("DATABASE_URL", None)

def start() -> scoped_session:
    db_url = (
        DB_URI.replace("postgres://", "postgresql://")
        if "postgres://" in DB_URI
        else DB_URI
    )
    engine = create_engine(db_url)
    BASE.metadata.bind = engine
    BASE.metadata.create_all(engine)
    return scoped_session(sessionmaker(bind=engine, autoflush=False))


try:
    BASE = declarative_base()
    SESSION = start()
except Exception as e:
    print("DB_URI is not configured!", str(e))

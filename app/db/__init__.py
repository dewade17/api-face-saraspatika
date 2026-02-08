from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from flask import current_app

Base = declarative_base()
_SessionFactory = None
_engine = None

def get_engine():
    global _engine
    if _engine is None:
        url = current_app.config.get("DATABASE_URL", "")
        if not url:
            raise RuntimeError("DATABASE_URL not configured")
        _engine = create_engine(url, pool_pre_ping=True, future=True)
    return _engine

def get_session():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False, future=True)
    return _SessionFactory()

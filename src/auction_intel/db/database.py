"""Conexão com o banco (SQLite local por padrão, PostgreSQL via DATABASE_URL)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from auction_intel.config import settings

# check_same_thread só existe (e só é necessário) no SQLite
_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependência do FastAPI: abre uma sessão por requisição."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_DB_PATH = os.path.join(APP_ROOT, "database", "app.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.replace(os.sep, '/')}")

SQLITE_JOURNAL_MODE = os.environ.get("SQLITE_JOURNAL_MODE", "WAL").upper()


def _sqlite_filesystem_path(url: str) -> str | None:
    if not url.startswith("sqlite:///"):
        return None
    raw = url[len("sqlite:///") :]
    if raw.startswith("/"):
        return raw
    if os.name == "nt" and len(raw) > 1 and raw[1] == ":":
        return raw
    return os.path.join(APP_ROOT, raw)


DB_PATH = _sqlite_filesystem_path(DATABASE_URL) or DEFAULT_DB_PATH
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

_connect_args: dict = {}
_engine_kwargs: dict = {"pool_pre_ping": True}

if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False, "timeout": 30}
    _engine_kwargs["poolclass"] = NullPool

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    **_engine_kwargs,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record):
    if not DATABASE_URL.startswith("sqlite"):
        return
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute(f"PRAGMA journal_mode={SQLITE_JOURNAL_MODE}")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_session():
    return SessionLocal()


def init_db() -> None:
    from app.db import models  # noqa: F401

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    Base.metadata.create_all(bind=engine)

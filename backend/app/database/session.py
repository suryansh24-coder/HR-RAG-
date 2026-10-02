"""SQLAlchemy engine and session management.

* **SQLite** is the default so the project runs with zero infrastructure. The
  database file is anchored to the project root, so the app behaves the same no
  matter which directory uvicorn was started from.
* **PostgreSQL** is supported for production via ``DATABASE_URL``
  (``postgresql+psycopg://user:pass@host:5432/db``); the driver ships in
  ``requirements.txt``, so changing the URL is the only step required.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)

SQLITE_PREFIX = "sqlite:///./"


def resolve_database_url(url: str) -> str:
    """Anchor relative SQLite paths to the project root."""
    if url.startswith(SQLITE_PREFIX):
        path = PROJECT_ROOT / url.replace(SQLITE_PREFIX, "")
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.as_posix()}"
    return url


def build_engine(url: str | None = None) -> Engine:
    database_url = url or settings.DATABASE_URL
    is_sqlite = database_url.startswith("sqlite")

    connect_args: dict = {"check_same_thread": False} if is_sqlite else {}
    if is_sqlite:
        connect_args["timeout"] = 30

    engine = create_engine(
        resolve_database_url(database_url),
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=5 if not is_sqlite else 5,
        max_overflow=10 if not is_sqlite else 0,
        echo=settings.DB_ECHO,
        future=True,
    )

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _enable_sqlite_pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context-managed session for background tasks, scripts and tests."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create missing tables, then add any column the models gained since.

    ``create_all`` only creates tables, so a database written by an older version
    of the app would keep its old shape and fail at query time on a newer column.
    ``sync_schema`` closes that gap with additive ``ADD COLUMN`` statements only —
    see :mod:`app.database.schema_sync` for what it deliberately refuses to do.
    """
    from app.models import entities  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)

    from app.database.schema_sync import sync_schema

    applied = sync_schema(engine)
    if applied:
        logger.info("Applied %d schema column(s) to an existing database", len(applied))

"""SQLAlchemy engine/session setup.

Uses SQLite by default (a single file database — zero install). The same
models work with any SQLAlchemy URL, so a server database like PostgreSQL can
be swapped in via DATABASE_URL without code changes.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True}
    if settings.is_sqlite:
        # FastAPI may touch the session from different threads; a file-based
        # SQLite DB is fine as long as cross-thread usage is allowed.
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they do not exist, plus a lightweight column migration
    for existing SQLite databases (Alembic optional for the prototype)."""
    from app import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
    if settings.is_sqlite:
        from sqlalchemy import text

        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(trains)"))]
            if cols and "live_enabled" not in cols:
                conn.execute(text("ALTER TABLE trains ADD COLUMN live_enabled BOOLEAN DEFAULT 0"))
                # preserve previous behaviour: trains whose latest REAL snapshot
                # (LIVE/CACHED/SEED) shows a running journey start with live ON
                conn.execute(text(
                    """
                    UPDATE trains SET live_enabled = 1 WHERE id IN (
                        SELECT train_id FROM (
                            SELECT train_id, status, MAX(id) AS max_id
                            FROM train_state_snapshots
                            WHERE data_source IN ('LIVE','CACHED','SEED')
                            GROUP BY train_id
                        ) WHERE status = 'running'
                    )
                    """
                ))
                conn.commit()

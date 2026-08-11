from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


url = settings.sqlalchemy_url
parsed = make_url(str(url)) if isinstance(url, str) else url
engine_kwargs: dict = {
    "echo": settings.sql_echo,
    "pool_pre_ping": True,
}
if parsed.drivername.startswith("mysql"):
    engine_kwargs.update(
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args=settings.db_connect_args,
    )

engine = create_engine(url, **engine_kwargs)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def ensure_database_exists() -> None:
    """Create the configured MySQL database if it does not exist."""
    if not parsed.drivername.startswith("mysql"):
        return

    import re

    db_name = parsed.database or settings.db_name
    if not re.fullmatch(r"[A-Za-z0-9_]+", db_name):
        raise ValueError("DB_NAME may only contain letters, numbers, and underscore")

    server_url = URL.create(
        parsed.drivername,
        username=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port,
        query={"charset": "utf8mb4"},
    )
    admin_engine = create_engine(
        server_url,
        pool_pre_ping=True,
        connect_args=settings.db_connect_args,
    )
    try:
        with admin_engine.begin() as conn:
            conn.execute(text(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            ))
    finally:
        admin_engine.dispose()

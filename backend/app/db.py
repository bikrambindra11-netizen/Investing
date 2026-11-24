"""SQLite database via SQLAlchemy. Swap DATABASE_URL for PostgreSQL later."""
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    """One listed security. Filled from the exchange instrument lists in Phase 2."""

    __tablename__ = "instruments"

    instrument_key: Mapped[str] = mapped_column(String, primary_key=True)
    exchange: Mapped[str] = mapped_column(String, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    isin: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # NSE 4-level classification (Phase 3)
    macro_sector: Mapped[str | None] = mapped_column(String, nullable=True)
    sector: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    basic_industry: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class CacheEntry(Base):
    """Generic cache for slow-changing fetched data (macro, fundamentals)."""

    __tablename__ = "cache"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


def _make_engine(url: str):
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    Base.metadata.create_all(engine)

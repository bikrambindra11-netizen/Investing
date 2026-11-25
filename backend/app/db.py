"""SQLite database via SQLAlchemy. Swap DATABASE_URL for PostgreSQL later."""
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import Date, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    """One listed equity on one exchange (a company on NSE and BSE has two rows)."""

    __tablename__ = "instruments"

    instrument_key: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. NSE_EQ|INE002A01018
    exchange: Mapped[str] = mapped_column(String, index=True)  # NSE / BSE
    symbol: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    isin: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    series: Mapped[str | None] = mapped_column(String, nullable=True)  # NSE series / BSE group
    # NSE 4-level classification (Phase 3)
    macro_sector: Mapped[str | None] = mapped_column(String, nullable=True)
    sector: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    basic_industry: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DailyPrice(Base):
    """End-of-day prices from the exchange bhavcopy files."""

    __tablename__ = "daily_prices"

    instrument_key: Mapped[str] = mapped_column(String, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)  # rupees
    source: Mapped[str] = mapped_column(String)


class IndexClose(Base):
    """End-of-day index values."""

    __tablename__ = "index_closes"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String)


class UpstoxToken(Base):
    """The daily Upstox access token from the login flow (single row)."""

    __tablename__ = "upstox_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    access_token: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class CacheEntry(Base):
    """Generic cache for slow-changing fetched data (macro, fundamentals)."""

    __tablename__ = "cache"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


def _make_engine(url: str):
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    # Phase 1 created an instruments table without the `series` column. It only ever held
    # an empty table, so drop and recreate it if it is the old shape.
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if insp.has_table("instruments"):
        cols = {c["name"] for c in insp.get_columns("instruments")}
        if "series" not in cols:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE instruments"))
    Base.metadata.create_all(engine)


class MacroPoint(Base):
    """One observation of a macro indicator."""

    __tablename__ = "macro_points"

    series_id: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)  # ISO date
    value: Mapped[float] = mapped_column(Float)

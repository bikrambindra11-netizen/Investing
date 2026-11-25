"""Data refresh jobs and the live-feed manager."""
import asyncio
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from backend.sources import bhavcopy, nse_indices, upstox_feed, upstox_instruments

from .config import settings
from .db import DailyPrice, IndexClose, Instrument, SessionLocal, UpstoxToken, utcnow
from .live import live
from .market_data import build_rows, live_subscription_keys

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

# Last outcome of each job, shown on the status endpoint.
job_status: dict[str, dict] = {}


def _record(name: str, ok: bool, detail: str) -> None:
    job_status[name] = {"ok": ok, "detail": detail, "at": datetime.now(timezone.utc).isoformat()}
    (log.info if ok else log.error)("%s: %s", name, detail)


def today_ist() -> date:
    return datetime.now(IST).date()


def refresh_instruments() -> None:
    try:
        rows = upstox_instruments.fetch()
        with SessionLocal() as s:
            existing = {i.instrument_key: i for i in s.scalars(select(Instrument))}
            for r in rows:
                ins = existing.get(r.instrument_key)
                if ins is None:
                    s.add(Instrument(instrument_key=r.instrument_key, exchange=r.exchange,
                                     symbol=r.symbol, name=r.name, isin=r.isin, series=r.series))
                else:  # keep any industry classification already stored
                    ins.symbol, ins.name, ins.isin, ins.series = r.symbol, r.name, r.isin, r.series
                    ins.updated_at = utcnow()
            s.commit()
        _record("instruments", True, f"{len(rows)} equity listings loaded")
    except Exception as e:
        _record("instruments", False, str(e))


def refresh_prices() -> None:
    for ex in ("NSE", "BSE"):
        try:
            rows = bhavcopy.fetch_latest(ex, today_ist())
            d = rows[0].trade_date if rows else None
            with SessionLocal() as s:
                s.execute(delete(DailyPrice).where(DailyPrice.trade_date == d,
                                                   DailyPrice.instrument_key.like(f"{ex}_EQ|%")))
                s.add_all(DailyPrice(instrument_key=r.instrument_key, trade_date=r.trade_date,
                                     open=r.open, high=r.high, low=r.low, close=r.close,
                                     prev_close=r.prev_close, volume=r.volume, turnover=r.turnover,
                                     source=bhavcopy.SOURCES[ex]) for r in rows)
                s.commit()
            _record(f"prices_{ex.lower()}", True, f"{len(rows)} prices for {d}")
        except Exception as e:
            _record(f"prices_{ex.lower()}", False, str(e))


def refresh_indices() -> None:
    try:
        rows = nse_indices.fetch_latest(today_ist())
        with SessionLocal() as s:
            for r in rows:
                s.merge(IndexClose(name=r.name, trade_date=r.trade_date, close=r.close,
                                   change=r.change, change_pct=r.change_pct, source=nse_indices.SOURCE))
            s.commit()
        _record("indices", True, f"{len(rows)} indices for {rows[0].trade_date if rows else '-'}")
    except Exception as e:
        _record("indices", False, str(e))


def refresh_all() -> None:
    refresh_instruments()
    refresh_prices()
    refresh_indices()


# ---------------------------------------------------------------- live feed

def current_token() -> str | None:
    """Today's token from the login flow, else UPSTOX_ACCESS_TOKEN from .env."""
    with SessionLocal() as s:
        t = s.get(UpstoxToken, 1)
        if t and t.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
            return t.access_token
    return settings.upstox_access_token or None


def save_token(token: str, expires_at: datetime) -> None:
    with SessionLocal() as s:
        s.merge(UpstoxToken(id=1, access_token=token, created_at=utcnow(),
                            expires_at=expires_at.astimezone(timezone.utc).replace(tzinfo=None)))
        s.commit()


class FeedManager:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self.stop()
        token = current_token()
        if not token:
            live.set_status("needs_keys" if not settings.upstox_api_key else "needs_login",
                            None)
            return
        with SessionLocal() as s:
            rows, _ = build_rows(s)
        keys = live_subscription_keys(rows, settings.live_max_instruments)
        self._task = asyncio.create_task(upstox_feed.run_feed(
            token, keys, on_ticks=live.update, on_status=live.set_status,
            on_market_info=lambda seg: live.segment_status.update(seg)))

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        live.clear()


feed = FeedManager()

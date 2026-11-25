"""Builds the market page data (one row per company) from the database."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.sources import bhavcopy, nse_indices

from .db import DailyPrice, IndexClose, Instrument
from .macro import resolve_industry

IST = ZoneInfo("Asia/Kolkata")

# (tile label, name in NSE's index close file or None, Upstox live instrument key)
INDEX_TILES = [
    ("Nifty 50", "Nifty 50", "NSE_INDEX|Nifty 50"),
    ("Sensex", None, "BSE_INDEX|SENSEX"),
    ("Nifty Bank", "Nifty Bank", "NSE_INDEX|Nifty Bank"),
    ("Nifty IT", "Nifty IT", "NSE_INDEX|Nifty IT"),
    ("Nifty Pharma", "Nifty Pharma", "NSE_INDEX|Nifty Pharma"),
    ("Nifty Auto", "Nifty Auto", "NSE_INDEX|Nifty Auto"),
    ("Nifty FMCG", "Nifty FMCG", "NSE_INDEX|Nifty FMCG"),
    ("Nifty Metal", "Nifty Metal", "NSE_INDEX|Nifty Metal"),
    ("Nifty Energy", "Nifty Energy", "NSE_INDEX|Nifty Energy"),
    ("Nifty Realty", "Nifty Realty", "NSE_INDEX|Nifty Realty"),
]


def pct_change(price: float | None, prev: float | None) -> float | None:
    if price is None or not prev:
        return None
    return round((price - prev) / prev * 100, 2)


def market_hours_open(now: datetime) -> bool:
    """Regular session by the clock: Mon-Fri 09:15-15:30 IST. Exchange holidays not checked."""
    local = now.astimezone(IST)
    return local.weekday() < 5 and time(9, 15) <= local.time() <= time(15, 30)


def _latest_date(s: Session, exchange: str) -> date | None:
    return s.scalar(select(func.max(DailyPrice.trade_date))
                    .where(DailyPrice.instrument_key.like(f"{exchange}_EQ|%")))


def build_rows(s: Session) -> tuple[list[dict], dict]:
    instruments = s.scalars(select(Instrument)).all()
    as_of = {ex: _latest_date(s, ex) for ex in ("NSE", "BSE")}
    prices: dict[str, DailyPrice] = {}
    for d in as_of.values():
        if d:
            for p in s.scalars(select(DailyPrice).where(DailyPrice.trade_date == d)):
                prices[p.instrument_key] = p

    by_isin: dict[str, list[Instrument]] = {}
    for ins in instruments:
        by_isin.setdefault(ins.isin or ins.instrument_key, []).append(ins)

    rows = []
    for group in by_isin.values():
        group.sort(key=lambda i: i.exchange != "NSE")  # NSE first
        primary = group[0]
        price = next((prices[i.instrument_key] for i in group if i.instrument_key in prices), None)
        price_ex = price.instrument_key.split("_")[0] if price else None
        rows.append({
            "key": primary.instrument_key,
            "symbol": primary.symbol,
            "name": primary.name,
            "isin": primary.isin,
            "exchanges": [i.exchange for i in group],
            "bse_symbol": next((i.symbol for i in group if i.exchange == "BSE"), None),
            "series": primary.series,
            "close": price.close if price else None,
            "prev_close": price.prev_close if price else None,
            "change_pct": pct_change(price.close, price.prev_close) if price else None,
            "volume": price.volume if price else None,
            "turnover": price.turnover if price else None,
            "price_date": price.trade_date.isoformat() if price else None,
            "price_source": bhavcopy.SOURCES[price_ex] if price else None,
            "sector": next((i.sector for i in group if i.sector), None),
            "industry": resolve_industry(None, primary.name, next((i.sector for i in group if i.sector), None)),
        })
    rows.sort(key=lambda r: -(r["turnover"] or 0))
    return rows, {ex: (d.isoformat() if d else None) for ex, d in as_of.items()}


def build_index_tiles(s: Session) -> list[dict]:
    latest = s.scalar(select(func.max(IndexClose.trade_date)))
    closes = {}
    if latest:
        closes = {r.name: r for r in s.scalars(select(IndexClose).where(IndexClose.trade_date == latest))}
    tiles = []
    for label, eod_name, live_key in INDEX_TILES:
        r = closes.get(eod_name) if eod_name else None
        tiles.append({
            "label": label,
            "key": live_key,
            "close": r.close if r else None,
            "change": r.change if r else None,
            "change_pct": r.change_pct if r else None,
            "as_of": r.trade_date.isoformat() if r else None,
            "source": nse_indices.SOURCE if r else None,
        })
    return tiles


def live_subscription_keys(rows: list[dict], limit: int) -> list[str]:
    """Indices first, then stocks by turnover (rows are already sorted that way)."""
    keys = [k for _, _, k in INDEX_TILES]
    keys += [r["key"] for r in rows]
    return keys[:limit]

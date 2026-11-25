"""End-of-day NSE index values from NSE's daily index close file."""
import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .http import NotFound, cached_download

URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{d}.csv"
SOURCE = "NSE index close file"


@dataclass(frozen=True)
class IndexRow:
    name: str
    trade_date: date
    close: float | None
    change: float | None
    change_pct: float | None


def _num(v: str) -> float | None:
    v = (v or "").strip()
    try:
        return float(v) if v and v != "-" else None
    except ValueError:
        return None


def parse(text: str) -> list[IndexRow]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        out.append(IndexRow(
            name=r["Index Name"].strip(),
            trade_date=datetime.strptime(r["Index Date"].strip(), "%d-%m-%Y").date(),
            close=_num(r["Closing Index Value"]),
            change=_num(r["Points Change"]),
            change_pct=_num(r["Change(%)"]),
        ))
    return out


def fetch_latest(today: date, lookback_days: int = 10) -> list[IndexRow]:
    for i in range(lookback_days):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        ds = d.strftime("%d%m%Y")
        try:
            raw = cached_download(URL.format(d=ds), f"nse_ind_close_{ds}.csv")
        except NotFound:
            continue
        return parse(raw.decode("utf-8", "replace"))
    raise NotFound(f"no NSE index file in the last {lookback_days} days")

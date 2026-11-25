"""End-of-day prices from NSE and BSE bhavcopy files (common UDiFF CSV format).

The files appear some hours after the close, so we look back up to 10 days for the
most recent one that exists.
"""
import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta

from .http import NotFound, cached_download

NSE_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d}_F_0000.csv.zip"
BSE_URL = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d}_F_0000.CSV"
SOURCES = {"NSE": "NSE bhavcopy", "BSE": "BSE bhavcopy"}
# NSE regular trading series. Others (e.g. BL = block-deal window) are skipped so that a
# block trade never sets a stock's price.
NSE_EQUITY_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}


@dataclass(frozen=True)
class PriceRow:
    exchange: str
    isin: str
    symbol: str
    trade_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    prev_close: float | None
    volume: int | None
    turnover: float | None

    @property
    def instrument_key(self) -> str:
        return f"{self.exchange}_EQ|{self.isin}"


def _num(v: str) -> float | None:
    v = (v or "").strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


def parse(text: str, exchange: str) -> list[PriceRow]:
    """Parse a UDiFF bhavcopy CSV. Keeps company equity rows (ISIN starting INE)."""
    if not text.lstrip().startswith("TradDt"):
        raise ValueError(f"{exchange} bhavcopy is not a CSV (got an HTML page?)")
    rows, seen = [], set()
    for r in csv.DictReader(io.StringIO(text)):
        isin = (r.get("ISIN") or "").strip()
        if r.get("FinInstrmTp") != "STK" or not isin.startswith("INE") or isin in seen:
            continue
        if exchange == "NSE" and (r.get("SctySrs") or "").strip() not in NSE_EQUITY_SERIES:
            continue
        seen.add(isin)
        vol = _num(r.get("TtlTradgVol", ""))
        rows.append(PriceRow(
            exchange=exchange,
            isin=isin,
            symbol=r["TckrSymb"].strip(),
            trade_date=date.fromisoformat(r["TradDt"]),
            open=_num(r["OpnPric"]),
            high=_num(r["HghPric"]),
            low=_num(r["LwPric"]),
            close=_num(r["ClsPric"]),
            prev_close=_num(r["PrvsClsgPric"]),
            volume=int(vol) if vol is not None else None,
            turnover=_num(r.get("TtlTrfVal", "")),
        ))
    return rows


def _fetch_day(exchange: str, d: date) -> list[PriceRow]:
    ds = d.strftime("%Y%m%d")
    if exchange == "NSE":
        raw = cached_download(NSE_URL.format(d=ds), f"nse_bhav_{ds}.csv.zip")
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            text = z.read(z.namelist()[0]).decode("utf-8", "replace")
    else:
        raw = cached_download(BSE_URL.format(d=ds), f"bse_bhav_{ds}.csv",
                              headers={"Referer": "https://www.bseindia.com/"})
        text = raw.decode("utf-8", "replace")
        if not text.lstrip().startswith("TradDt"):
            # BSE answers a missing file with its home page instead of a 404.
            from .http import RAW_DIR
            (RAW_DIR / f"bse_bhav_{ds}.csv").unlink(missing_ok=True)
            raise NotFound(ds)
    return parse(text, exchange)


def fetch_latest(exchange: str, today: date, lookback_days: int = 10) -> list[PriceRow]:
    """Most recent bhavcopy on or before `today`. Raises NotFound if none in the window."""
    for i in range(lookback_days):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:  # Saturday/Sunday
            continue
        try:
            return _fetch_day(exchange, d)
        except NotFound:
            continue
    raise NotFound(f"no {exchange} bhavcopy in the last {lookback_days} days")

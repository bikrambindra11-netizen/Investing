"""Delivery quantity and delivery % per stock from NSE's full bhavcopy (sec_bhavdata_full), no key needed."""
import csv
import io
from datetime import date, timedelta

from .http import NotFound, cached_download

URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d}.csv"
SOURCE = "NSE full bhavcopy (delivery data)"


def parse(text: str) -> dict[str, dict]:
    out = {}
    for r in csv.DictReader(io.StringIO(text), skipinitialspace=True):
        r = {k.strip(): (v or "").strip() for k, v in r.items()}
        if r.get("SERIES") not in ("EQ", "BE", "BZ", "SM", "ST"):
            continue
        try:
            pct = float(r["DELIV_PER"]) if r["DELIV_PER"] not in ("", "-") else None
            out[r["SYMBOL"]] = {"volume": int(float(r["TTL_TRD_QNTY"])), "delivery_qty": int(float(r["DELIV_QTY"])) if r["DELIV_QTY"] not in ("", "-") else None,
                                "delivery_pct": pct, "date": r["DATE1"]}
        except (KeyError, ValueError):
            continue
    return out


def recent(today: date, days: int = 5, lookback: int = 12) -> list[dict[str, dict]]:
    """The last `days` trading days of delivery data, newest first."""
    out = []
    for i in range(lookback):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        ds = d.strftime("%d%m%Y")
        try:
            raw = cached_download(URL.format(d=ds), f"nse_full_bhav_{ds}.csv")
        except NotFound:
            continue
        text = raw.decode("utf-8", "replace")
        if not text.startswith("SYMBOL"):
            continue
        out.append(parse(text))
        if len(out) >= days:
            break
    return out


def summary(symbol: str, data: list[dict[str, dict]]) -> dict:
    rows = [d[symbol] for d in data if symbol in d]
    if not rows:
        return {"available": False}
    pcts = [r["delivery_pct"] for r in rows if r["delivery_pct"] is not None]
    return {"available": True, "latest": rows[0], "avg_delivery_pct": round(sum(pcts) / len(pcts), 1) if pcts else None,
            "days": len(rows), "source": SOURCE}

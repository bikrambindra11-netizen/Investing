"""Historical daily candles from Upstox (API v3). Works without an access token."""
from datetime import date, timedelta
from urllib.parse import quote

import httpx

from . import cache

URL = "https://api.upstox.com/v3/historical-candle/{key}/days/1/{to}/{frm}"
SOURCE = "Upstox historical candles"


def parse(payload: dict) -> list[dict]:
    """Upstox returns newest first: [ts, open, high, low, close, volume, oi]. We return oldest first."""
    out = []
    for c in (payload.get("data") or {}).get("candles") or []:
        out.append({"date": c[0][:10], "open": c[1], "high": c[2], "low": c[3], "close": c[4],
                    "volume": c[5]})
    out.sort(key=lambda r: r["date"])
    return out


def _fetch(instrument_key: str, to: date, token: str | None) -> list[dict]:
    frm = to - timedelta(days=3650)  # v3 allows one decade of daily candles per call
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    last = None
    for _ in range(3):
        try:
            r = httpx.get(URL.format(key=quote(instrument_key, safe=""), to=to.isoformat(),
                                     frm=frm.isoformat()), headers=headers, timeout=30)
            r.raise_for_status()
            return parse(r.json())
        except httpx.HTTPError as e:
            last = e
    raise RuntimeError(f"Upstox candles failed for {instrument_key}: {last}")


def daily(instrument_key: str, today: date, token: str | None = None) -> tuple[list[dict], object]:
    """Up to 10 years of daily candles, cached for 6 hours."""
    return cache.get_or_fetch(f"candles:{instrument_key}", SOURCE, timedelta(hours=6),
                              lambda: _fetch(instrument_key, today, token))

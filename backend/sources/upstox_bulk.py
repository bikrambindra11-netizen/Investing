"""Bulk Upstox data with the long-lived Analytics Token (sent by the network proxy, or UPSTOX_ACCESS_TOKEN).

- fundamentals for many companies, kept in a JSON cache between runs and refreshed a batch at a time
- last traded prices for every stock (500 instruments per request)
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "https://api.upstox.com/v2"
SOURCE = "Upstox (Analytics Token)"
ENDPOINTS = {
    "profile": ("profile", {}),
    "income": ("income-statement", {"type": "consolidated", "time_period": "yearly", "fs": "true"}),
    "income_q": ("income-statement", {"type": "consolidated", "time_period": "quarterly"}),
    "balance": ("balance-sheet", {"type": "consolidated", "fs": "true"}),
    "cashflow": ("cash-flow", {"type": "consolidated", "fs": "true"}),
    "ratios": ("key-ratios", {}),
    "holdings": ("share-holdings", {}),
    "actions": ("corporate-actions", {}),
}


def _client() -> httpx.Client:
    # The proxy replaces this header with the saved token; locally a real token can be set in the env.
    token = os.environ.get("UPSTOX_ACCESS_TOKEN") or "proxy-injected"
    return httpx.Client(headers={"Accept": "application/json", "Authorization": f"Bearer {token}"}, timeout=30)


def _get(c: httpx.Client, path: str, params: dict | None = None) -> dict | list | None:
    for attempt in range(4):
        try:
            r = c.get(BASE + path, params=params)
        except httpx.HTTPError:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code in (401, 403):
            raise PermissionError("Upstox rejected the token")
        body = r.json()
        return body.get("data") if body.get("status") == "success" else None
    return None


def fetch_company(c: httpx.Client, isin: str, instrument_key: str) -> dict:
    out = {}
    for name, (path, params) in ENDPOINTS.items():
        data = _get(c, f"/fundamentals/{isin}/{path}", params)
        if data is None and params.get("type") == "consolidated":
            data = _get(c, f"/fundamentals/{isin}/{path}", {**params, "type": "standalone"})
        out[name] = data
    out["competitors"] = _get(c, f"/fundamentals/{instrument_key}/competitors")
    out["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def refresh_cache(cache_path: Path, universe: list[tuple[str, str]], budget: int, max_age_days: float = 7) -> dict:
    """Fetch fundamentals for up to `budget` companies that are missing or older than max_age_days.

    universe: [(isin, instrument_key)] in priority order. Returns the whole cache {isin: data}.
    """
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    now = datetime.now(timezone.utc)

    def age(isin: str) -> float:
        e = cache.get(isin)
        if not e:
            return 1e9
        return (now - datetime.fromisoformat(e["fetched_at"])).total_seconds() / 86400

    todo = [(i, k) for i, k in universe if age(i) > max_age_days]
    todo.sort(key=lambda x: -age(x[0]))  # missing first, then oldest
    todo = todo[:budget]
    if todo:
        with _client() as c, ThreadPoolExecutor(3) as ex:
            for (isin, _), data in zip(todo, ex.map(lambda t: fetch_company(c, *t), todo)):
                if data.get("income") or data.get("ratios") or data.get("profile"):
                    cache[isin] = data
    keep = {i for i, _ in universe}
    cache = {i: v for i, v in cache.items() if i in keep}
    cache_path.write_text(json.dumps(cache, separators=(",", ":")))
    return cache


def last_prices(keys: list[str]) -> dict[str, float]:
    """{instrument_key: last traded price} for any number of instruments."""
    out: dict[str, float] = {}
    with _client() as c:
        for i in range(0, len(keys), 500):
            data = _get(c, "/market-quote/ltp", {"instrument_key": ",".join(keys[i:i + 500])}) or {}
            for v in data.values():
                if v.get("instrument_token") and v.get("last_price") is not None:
                    out[v["instrument_token"]] = v["last_price"]
    return out

"""Upstox Company Fundamentals API (needs the daily Upstox access token).

All money values are in ₹ crore. Periods look like "Mar 2025".
"""
import time
from datetime import timedelta

import httpx

from . import cache

BASE = "https://api.upstox.com/v2/fundamentals/{isin}/{path}"
SOURCE = "Upstox fundamentals"

ENDPOINTS = {
    "profile": ("profile", {}),
    "income": ("income-statement", {"type": "consolidated", "time_period": "yearly", "fs": "true"}),
    "income_q": ("income-statement", {"type": "consolidated", "time_period": "quarterly"}),
    "balance": ("balance-sheet", {"type": "consolidated", "fs": "true"}),
    "cashflow": ("cash-flow", {"type": "consolidated", "fs": "true"}),
    "ratios": ("key-ratios", {}),
    "holdings": ("share-holdings", {}),
    "actions": ("corporate-actions", {}),
    "competitors": ("competitors", {}),
}


class NeedsLogin(Exception):
    pass


def _get(isin: str, path: str, params: dict, token: str) -> object:
    for attempt in range(5):  # wait and retry when Upstox says "too many requests"
        r = httpx.get(BASE.format(isin=isin, path=path), params=params, timeout=30,
                      headers={"Accept": "application/json", "Authorization": f"Bearer {token}"})
        if r.status_code != 429:
            break
        time.sleep(2 * (attempt + 1))
    if r.status_code in (401, 403):
        raise NeedsLogin(r.text[:200])
    if r.status_code >= 400:
        raise RuntimeError(f"Upstox {path} HTTP {r.status_code}: {r.text[:200]}")
    body = r.json()
    if body.get("status") != "success":
        raise RuntimeError(f"Upstox {path}: {body}")
    return body.get("data")


def fetch_all(isin: str, token: str | None) -> dict:
    """{name: {"data": ..., "fetched_at": iso} | {"error": msg}} for every endpoint.

    Cached for 7 days per ISIN and endpoint. Without a token, returns cached data only.
    """
    out = {}
    for name, (path, params) in ENDPOINTS.items():
        key = f"fund:{isin}:{name}"
        try:
            if token:
                # Standalone fallback when a company has no consolidated statements.
                def fetch(path=path, params=params):
                    try:
                        return _get(isin, path, params, token)
                    except RuntimeError:
                        if params.get("type") == "consolidated":
                            return _get(isin, path, {**params, "type": "standalone"}, token)
                        raise
                data, at = cache.get_or_fetch(key, SOURCE, timedelta(days=7), fetch)
            else:
                hit = cache.get(key, None)
                if not hit:
                    raise NeedsLogin("no Upstox login")
                data, at = hit
            out[name] = {"data": data, "fetched_at": at.isoformat()}
        except NeedsLogin as e:
            out[name] = {"error": "needs_login", "detail": str(e)}
        except Exception as e:
            out[name] = {"error": "failed", "detail": str(e)}
    return out

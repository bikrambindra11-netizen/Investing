"""Upstox OAuth login: builds the login URL and swaps the returned code for a daily token.

Upstox access tokens stop working at 3:30 AM IST the next day, so the user logs in once a day.
"""
from datetime import datetime, time, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

IST = ZoneInfo("Asia/Kolkata")
DIALOG_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


def login_url(api_key: str, redirect_uri: str, state: str) -> str:
    q = urlencode({"response_type": "code", "client_id": api_key,
                   "redirect_uri": redirect_uri, "state": state})
    return f"{DIALOG_URL}?{q}"


def token_expiry(issued_at: datetime) -> datetime:
    """The 3:30 AM IST that follows `issued_at` (returned timezone-aware, in IST)."""
    local = issued_at.astimezone(IST)
    cutoff = datetime.combine(local.date(), time(3, 30), tzinfo=IST)
    return cutoff if local < cutoff else cutoff + timedelta(days=1)


def exchange_code(code: str, api_key: str, api_secret: str, redirect_uri: str) -> str:
    """Swap the one-time login code for an access token."""
    r = httpx.post(
        TOKEN_URL,
        data={"code": code, "client_id": api_key, "client_secret": api_secret,
              "redirect_uri": redirect_uri, "grant_type": "authorization_code"},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Upstox token exchange failed (HTTP {r.status_code}): {r.text[:300]}")
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("Upstox did not return an access token")
    return token

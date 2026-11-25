"""FastAPI entry point. Run: uvicorn backend.app.main:app --reload"""
import asyncio
import gzip
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from sqlalchemy import func, select

from backend.sources import upstox_auth

from . import jobs, macro, stock
from .config import settings
from .db import Instrument, SessionLocal, init_db
from .jobs import feed
from .live import live
from .market_data import build_index_tiles, build_rows, market_hours_open

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

_cache: dict = {}  # cached market rows, cleared after each data refresh
_login_states: set[str] = set()


async def _refresh_and_restart_feed() -> None:
    await asyncio.to_thread(jobs.refresh_all)
    _cache.clear()
    feed.start()


async def _refresh_macro() -> None:
    await asyncio.to_thread(jobs.refresh_macro)


async def _startup_refresh() -> None:
    await _refresh_and_restart_feed()
    await _refresh_macro()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    scheduler = None
    if settings.run_jobs:
        scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        # Instrument list every morning; bhavcopy files appear in the evening / next morning.
        scheduler.add_job(_refresh_and_restart_feed, "cron", day_of_week="mon-fri", hour=8, minute=30)
        scheduler.add_job(_refresh_and_restart_feed, "cron", day_of_week="mon-fri", hour="18,21", minute=5)
        scheduler.add_job(_refresh_macro, "cron", hour=7, minute=40)  # most macro series are monthly
        scheduler.start()
        asyncio.create_task(_startup_refresh())
    yield
    feed.stop()
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Stock Picker Portal API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict:
    with SessionLocal() as s:
        instrument_count = s.scalar(select(func.count()).select_from(Instrument))
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "database": "connected",
        "instruments": instrument_count,
        "keys_configured": settings.key_status(),
        "disclaimer": "Personal screening tool. Not investment advice.",
    }


# ------------------------------------------------------------------ market

@app.get("/api/market/stocks")
def market_stocks(request: Request) -> Response:
    """All stocks (one row per company). ~6,000 rows, so the body is gzipped and cached.

    (Not using GZipMiddleware: it would buffer the live SSE stream.)
    """
    if "stocks" not in _cache:
        with SessionLocal() as s:
            rows, as_of = build_rows(s)
        body = json.dumps({"as_of": as_of, "count": len(rows), "rows": rows}).encode()
        _cache["stocks"] = (body, gzip.compress(body, 6))
    body, zipped = _cache["stocks"]
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(zipped, media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return Response(body, media_type="application/json", headers={"Vary": "Accept-Encoding"})


@app.get("/api/market/indices")
def market_indices() -> list[dict]:
    with SessionLocal() as s:
        return build_index_tiles(s)


def _status() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "time": now.isoformat(),
        "market_open_by_clock": market_hours_open(now),
        "segment_status": live.segment_status,
        "live": {
            "state": live.state,
            "message": live.message,
            "last_tick_at": live.last_tick_at.isoformat() if live.last_tick_at else None,
            "source": "Upstox market data feed",
        },
        "upstox_keys_set": bool(settings.upstox_api_key and settings.upstox_api_secret),
        "jobs": jobs.job_status,
    }


@app.get("/api/market/status")
def market_status() -> dict:
    return _status()


@app.post("/api/market/refresh")
async def market_refresh() -> dict:
    asyncio.create_task(_refresh_and_restart_feed())
    return {"started": True}


def _tick_json(ticks: dict[str, dict]) -> dict:
    return {k: {"ltp": t["ltp"], "cp": t["cp"],
                "ltt": t["ltt"].isoformat() if t["ltt"] else None} for k, t in ticks.items()}


@app.get("/api/market/stream")
async def market_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events: `ticks` (changed prices, first one is a full snapshot) and `status`."""

    async def events():
        seq, n = 0, 0
        while not await request.is_disconnected():
            seq, changed = live.since(seq)
            if changed:
                yield f"event: ticks\ndata: {json.dumps(_tick_json(changed))}\n\n"
            if n % 5 == 0:
                yield f"event: status\ndata: {json.dumps(_status())}\n\n"
            n += 1
            await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ Upstox login

@app.get("/auth/upstox/login")
def upstox_login() -> RedirectResponse:
    if not (settings.upstox_api_key and settings.upstox_api_secret):
        raise HTTPException(400, "Add UPSTOX_API_KEY and UPSTOX_API_SECRET to .env, then restart the backend.")
    state = secrets.token_urlsafe(16)
    _login_states.add(state)
    return RedirectResponse(upstox_auth.login_url(settings.upstox_api_key, settings.upstox_redirect_uri, state))


@app.get("/auth/upstox/callback")
async def upstox_callback(code: str | None = None, state: str | None = None) -> RedirectResponse:
    if not code or state not in _login_states:
        raise HTTPException(400, "Invalid or expired login attempt. Start again from the market page.")
    _login_states.discard(state)
    try:
        token = await asyncio.to_thread(upstox_auth.exchange_code, code, settings.upstox_api_key,
                                        settings.upstox_api_secret, settings.upstox_redirect_uri)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    jobs.save_token(token, upstox_auth.token_expiry(datetime.now(timezone.utc)))
    feed.start()
    return RedirectResponse(f"{settings.frontend_origin}/?upstox=connected")


# ------------------------------------------------------------------ stock / industry / macro

@app.get("/api/stock/{isin}")
def stock_detail(isin: str) -> dict:
    data = stock.stock_page(isin.upper())
    if data is None:
        raise HTTPException(404, "Stock not found")
    return data


@app.get("/api/industries")
def industries() -> list[dict]:
    return stock.industries_list()


@app.get("/api/industry/{industry_id}")
def industry(industry_id: str) -> dict:
    data = stock.industry_page(industry_id)
    if data is None:
        raise HTTPException(404, "Industry not found")
    return data


@app.get("/api/macro")
def macro_dashboard() -> dict:
    return {"indicators": macro.all_indicators(), "status": jobs.job_status.get("macro")}


# ------------------------------------------------------------------ multi-timeframe charts

@app.get("/api/chart")
def chart_data(key: str, tf: str = "1D", bars: int | None = None) -> dict:
    from . import charts
    if tf not in charts.TIMEFRAMES:
        raise HTTPException(400, f"Unknown timeframe {tf}. Use one of {', '.join(charts.TIMEFRAMES)}.")
    return charts.chart(key, tf, bars)


@app.get("/api/mtf")
def multi_timeframe(key: str) -> list[dict]:
    from . import charts
    return charts.multi_timeframe(key)

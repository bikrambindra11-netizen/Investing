"""Upstox live market-data feed (WebSocket, protobuf, API v3).

We open the WebSocket ourselves (with TLS certificate checks on) and only borrow the
official SDK's protobuf message definitions for decoding.
"""
import asyncio
import json
import logging
import ssl
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

import httpx
import websockets
from google.protobuf import json_format
from upstox_client.feeder.proto import MarketDataFeedV3_pb2 as pb

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://api.upstox.com/v3/feed/market-data-feed/authorize"
SUBSCRIBE_BATCH = 500


class TokenRejected(Exception):
    """Upstox refused the access token (expired or invalid)."""


def parse_message(raw: bytes) -> tuple[dict[str, dict], dict[str, str]]:
    """Decode one feed message into ({instrument_key: tick}, {segment: status}).

    tick = {"ltp": float, "cp": float | None, "ltt": datetime | None}
    cp is the previous day's close, so change = ltp - cp.
    """
    msg = json_format.MessageToDict(pb.FeedResponse.FromString(raw))
    ticks: dict[str, dict] = {}
    for key, feed in (msg.get("feeds") or {}).items():
        ltpc = feed.get("ltpc")
        if ltpc is None:
            ff = feed.get("fullFeed") or {}
            ltpc = (ff.get("marketFF") or ff.get("indexFF") or {}).get("ltpc")
        if not ltpc or "ltp" not in ltpc:
            continue
        ltt = ltpc.get("ltt")
        ticks[key] = {
            "ltp": float(ltpc["ltp"]),
            "cp": float(ltpc["cp"]) if "cp" in ltpc else None,
            "ltt": datetime.fromtimestamp(int(ltt) / 1000, timezone.utc) if ltt else None,
        }
    status = (msg.get("marketInfo") or {}).get("segmentStatus") or {}
    return ticks, status


def build_subscribe(keys: list[str], mode: str = "ltpc") -> bytes:
    return json.dumps({"guid": str(uuid.uuid4()), "method": "sub",
                       "data": {"mode": mode, "instrumentKeys": keys}}).encode()


async def _authorized_url(token: str) -> str:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(AUTHORIZE_URL, headers={"Authorization": f"Bearer {token}",
                                                 "Accept": "application/json"})
    if r.status_code in (401, 403):
        raise TokenRejected(r.text[:200])
    r.raise_for_status()
    return r.json()["data"]["authorized_redirect_uri"]


async def run_feed(token: str, keys: list[str],
                   on_ticks: Callable[[dict[str, dict]], None],
                   on_status: Callable[[str, str | None], None],
                   on_market_info: Callable[[dict[str, str]], None] = lambda _: None) -> None:
    """Stay connected (reconnecting with backoff) until cancelled or the token is rejected."""
    delay = 2
    ctx = ssl.create_default_context()
    while True:
        try:
            on_status("connecting", None)
            url = await _authorized_url(token)
            async with websockets.connect(url, ssl=ctx, max_size=None, ping_interval=20) as ws:
                for i in range(0, len(keys), SUBSCRIBE_BATCH):
                    await ws.send(build_subscribe(keys[i:i + SUBSCRIBE_BATCH]))
                on_status("connected", f"subscribed to {len(keys)} instruments")
                delay = 2
                async for raw in ws:
                    if isinstance(raw, str):
                        continue
                    ticks, seg = parse_message(raw)
                    if seg:
                        on_market_info(seg)
                    if ticks:
                        on_ticks(ticks)
        except asyncio.CancelledError:
            raise
        except TokenRejected as e:
            on_status("token_rejected", f"Upstox rejected the token, please log in again ({e})")
            return
        except Exception as e:  # network drop, server close, etc.
            log.warning("upstox feed error: %s", e)
            on_status("reconnecting", f"connection lost ({e.__class__.__name__}); retrying in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

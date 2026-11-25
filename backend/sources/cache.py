"""JSON cache in the database (CacheEntry) for slow-changing data."""
import json
from datetime import datetime, timedelta, timezone

from backend.app.db import CacheEntry, SessionLocal


def get(key: str, max_age: timedelta | None) -> tuple[object, datetime] | None:
    """(payload, fetched_at UTC) if cached and fresh enough, else None."""
    with SessionLocal() as s:
        e = s.get(CacheEntry, key)
        if e is None:
            return None
        fetched = e.fetched_at.replace(tzinfo=timezone.utc)
        if max_age is not None and datetime.now(timezone.utc) - fetched > max_age:
            return None
        return json.loads(e.payload), fetched


def put(key: str, source: str, payload: object) -> datetime:
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        s.merge(CacheEntry(key=key, source=source, payload=json.dumps(payload),
                           fetched_at=now.replace(tzinfo=None)))
        s.commit()
    return now


def get_or_fetch(key: str, source: str, max_age: timedelta, fetch) -> tuple[object, datetime]:
    """Return cached payload, or call fetch() and cache it. On fetch failure, fall back to
    any older cached copy (stale data beats no data; its date is shown)."""
    hit = get(key, max_age)
    if hit:
        return hit
    try:
        payload = fetch()
    except Exception:
        stale = get(key, None)
        if stale:
            return stale
        raise
    return payload, put(key, source, payload)

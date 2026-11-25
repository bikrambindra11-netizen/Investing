"""Shared HTTP download helper with retries and an on-disk cache of raw files."""
import logging
import time
from pathlib import Path

import httpx

from backend.app.config import DATA_DIR

log = logging.getLogger(__name__)

RAW_DIR = DATA_DIR / "raw"
# Exchange archive servers reject requests without a browser-like User-Agent.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36",
    "Accept": "*/*",
}


class NotFound(Exception):
    """The file does not exist (yet) at the source."""


def download(url: str, *, headers: dict | None = None, retries: int = 3, timeout: float = 30) -> bytes:
    """GET a URL, retrying network errors and 5xx. Raises NotFound on 404."""
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = httpx.get(url, headers={**HEADERS, **(headers or {})}, timeout=timeout,
                          follow_redirects=True)
            if r.status_code == 404:
                raise NotFound(url)
            r.raise_for_status()
            return r.content
        except NotFound:
            raise
        except (httpx.HTTPError,) as e:
            last = e
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
                break
            log.warning("download failed (%s/%s) %s: %s", attempt, retries, url, e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"download failed: {url}: {last}")


def cached_download(url: str, filename: str, *, headers: dict | None = None,
                    max_age_s: float | None = None) -> bytes:
    """Download once and keep the raw file under backend/data/raw/.

    max_age_s=None means the file never changes (e.g. a past day's bhavcopy).
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path: Path = RAW_DIR / filename
    if path.exists() and (max_age_s is None or time.time() - path.stat().st_mtime < max_age_s):
        return path.read_bytes()
    data = download(url, headers=headers)
    path.write_bytes(data)
    return data

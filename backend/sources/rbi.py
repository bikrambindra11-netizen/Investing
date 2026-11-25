"""Current policy rates from the RBI home page (the rates panel shown on rbi.org.in)."""
import html
import re

from .http import download

URL = "https://www.rbi.org.in/"
SOURCE = "RBI website (current rates panel)"

PATTERNS = {
    "repo_rate": r"Policy Repo Rate\s*:\s*([\d.]+)\s*%",
    "crr": r"CRR\s*:\s*([\d.]+)\s*%",
    "slr": r"SLR\s*:\s*([\d.]+)\s*%",
    "tbill_91d": r"91 day T-bills\s*:\s*([\d.]+)\s*%",
}


def parse(page: str) -> dict[str, float]:
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    out = {}
    for k, pat in PATTERNS.items():
        m = re.search(pat, text)
        if m:
            out[k] = float(m.group(1))
    if "repo_rate" not in out:
        raise ValueError("repo rate not found on RBI page (layout may have changed)")
    return out


def fetch() -> dict[str, float]:
    return parse(download(URL).decode("utf-8", "replace"))

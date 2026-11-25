"""News headlines from Google News RSS, tagged positive / negative / neutral by simple rules."""
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from .http import download

URL = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
SOURCE = "Google News"

POSITIVE = [
    "surge", "surges", "soar", "soars", "jump", "jumps", "rally", "rallies", "gain", "gains", "rise", "rises",
    "record high", "beats", "beat estimates", "profit rises", "profit jumps", "upgrade", "upgraded", "buy rating",
    "outperform", "order win", "wins order", "bags order", "secures", "bagged", "expansion", "acquires",
    "dividend", "bonus", "buyback", "strong", "growth", "approval", "approved", "launches", "partnership",
    "rate cut", "boost", "upbeat", "robust", "all-time high", "top gainer", "raises guidance", "inflow",
    "rebound", "rebounds", "promoters buy", "promoter buys", "stake increase", "raises stake", "undervalued", "upside",
]
NEGATIVE = [
    "fall", "falls", "drop", "drops", "plunge", "plunges", "slump", "slumps", "crash", "tumble", "tumbles",
    "decline", "declines", "loss", "losses", "misses", "downgrade", "downgraded", "sell rating", "underperform",
    "probe", "raid", "penalty", "fine", "fined", "fraud", "default", "resigns", "resignation", "lawsuit",
    "ban", "warning", "weak", "cut guidance", "lowers guidance", "slowdown", "pledge", "outflow", "sebi notice",
    "rate hike", "headwind", "pressure", "top loser", "52-week low", "recall", "strike", "shutdown", "insolvency",
    "overvalued", "downside", "stake sale", "promoters sell", "cuts stake", "selloff", "sell-off",
]


def _count(words: list[str], text: str) -> int:
    return sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", text))


def sentiment(title: str) -> str:
    t = title.lower()
    p, n = _count(POSITIVE, t), _count(NEGATIVE, t)
    if p > n:
        return "positive"
    if n > p:
        return "negative"
    return "neutral"


def parse(xml: bytes, limit: int = 15) -> list[dict]:
    root = ET.fromstring(xml)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        publisher = (it.findtext("source") or "").strip()
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3]
        try:
            published = parsedate_to_datetime(it.findtext("pubDate") or "").isoformat()
        except (TypeError, ValueError):
            published = None
        items.append({"title": title, "link": it.findtext("link"), "publisher": publisher or None,
                      "published": published, "sentiment": sentiment(title)})
    items.sort(key=lambda x: x["published"] or "", reverse=True)
    return items[:limit]


def search(query: str, limit: int = 15) -> list[dict]:
    return parse(download(URL.format(q=quote_plus(query))), limit)

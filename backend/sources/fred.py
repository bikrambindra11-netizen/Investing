"""FRED (St. Louis Fed) series via the public CSV download (no API key needed)."""
import csv
import io

from .http import download

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}"
# FRED stalls requests that claim to be a web browser, so identify as an app.
HEADERS = {"User-Agent": "stock-picker-portal/1.0"}
SOURCE = "FRED (St. Louis Fed)"


def parse(text: str) -> list[tuple[str, float]]:
    if not text.startswith("observation_date"):
        raise ValueError("FRED did not return a CSV (series may be discontinued)")
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2 or row[0] == "observation_date" or row[1] in ("", "."):
            continue
        out.append((row[0], float(row[1])))
    return out


def fetch(series_id: str, start: str = "2019-01-01") -> list[tuple[str, float]]:
    raw = download(URL.format(id=series_id, start=start), headers=HEADERS, timeout=40)
    return parse(raw.decode("utf-8", "replace"))

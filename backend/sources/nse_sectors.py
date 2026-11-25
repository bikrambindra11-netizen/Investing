"""Sector classification from NSE index constituent lists (public CSV downloads).

These lists give NSE's 'Sector' level (e.g. "Capital Goods") for about 1,000 companies.
The Macro-Economic Sector above it follows from NSE's fixed classification structure.
"""
import csv
import io

from .http import NotFound, cached_download

URL = "https://nsearchives.nseindia.com/content/indices/{name}.csv"
SOURCE = "NSE index constituent lists"
LISTS = ["ind_niftytotalmarket_list", "ind_niftymicrocap250_list", "ind_nifty500list",
         "ind_niftysmallcap250list"]

# NSE Indices industry classification structure: Sector -> Macro-Economic Sector.
SECTOR_TO_MACRO = {
    "Chemicals": "Commodities",
    "Construction Materials": "Commodities",
    "Metals & Mining": "Commodities",
    "Forest Materials": "Commodities",
    "Automobile and Auto Components": "Consumer Discretionary",
    "Consumer Durables": "Consumer Discretionary",
    "Consumer Services": "Consumer Discretionary",
    "Media, Entertainment & Publication": "Consumer Discretionary",
    "Realty": "Consumer Discretionary",
    "Textiles": "Consumer Discretionary",
    "Oil Gas & Consumable Fuels": "Energy",
    "Fast Moving Consumer Goods": "Fast Moving Consumer Goods",
    "Financial Services": "Financial Services",
    "Healthcare": "Healthcare",
    "Capital Goods": "Industrials",
    "Construction": "Industrials",
    "Information Technology": "Information Technology",
    "Services": "Services",
    "Telecommunication": "Telecommunication",
    "Power": "Utilities",
    "Diversified": "Diversified",
}


def parse(text: str) -> dict[str, str]:
    """ISIN -> Sector."""
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        isin = (r.get("ISIN Code") or "").strip()
        sector = (r.get("Industry") or "").strip()
        if isin and sector:
            out[isin] = sector
    return out


def fetch() -> dict[str, str]:
    result: dict[str, str] = {}
    errors = []
    for name in LISTS:
        try:
            raw = cached_download(URL.format(name=name), f"{name}.csv", max_age_s=7 * 86400)
            for isin, sector in parse(raw.decode("utf-8", "replace")).items():
                result.setdefault(isin, sector)
        except (NotFound, RuntimeError) as e:
            errors.append(str(e))
    if not result:
        raise RuntimeError("no NSE index lists could be downloaded: " + "; ".join(errors))
    return result


INDEX_LISTS = {"Nifty 50": "ind_nifty50list", "Nifty Next 50": "ind_niftynext50list", "Nifty Midcap 150": "ind_niftymidcap150list",
               "Nifty Smallcap 250": "ind_niftysmallcap250list", "Nifty Microcap 250": "ind_niftymicrocap250_list",
               "Nifty 500": "ind_nifty500list", "Nifty Total Market": "ind_niftytotalmarket_list"}


def index_membership() -> dict[str, list[str]]:
    """ISIN -> NSE indices the company belongs to."""
    out: dict[str, list[str]] = {}
    for idx, name in INDEX_LISTS.items():
        try:
            raw = cached_download(URL.format(name=name), f"{name}.csv", max_age_s=7 * 86400)
        except (NotFound, RuntimeError):
            continue
        for isin in parse(raw.decode("utf-8", "replace")):
            out.setdefault(isin, []).append(idx)
    return out

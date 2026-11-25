"""Full NSE + BSE equity list from Upstox's public instrument file (no API key needed)."""
import gzip
import json
from dataclasses import dataclass

from .http import cached_download

URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
SOURCE = "Upstox instrument master"

# NSE equity series: EQ (main board), BE/BZ (trade-to-trade), SM/ST (SME platform).
NSE_EQUITY_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}
# BSE groups that are not equity shares: F = debt, G = government securities.
BSE_NON_EQUITY_GROUPS = {"F", "G"}


@dataclass(frozen=True)
class InstrumentRow:
    instrument_key: str
    exchange: str
    symbol: str
    name: str | None
    isin: str
    series: str


def parse(records: list[dict]) -> list[InstrumentRow]:
    """Keep only equity shares (company ISINs start with INE)."""
    out = []
    for x in records:
        seg, isin, typ = x.get("segment"), x.get("isin") or "", x.get("instrument_type")
        if seg == "NSE_EQ":
            if typ not in NSE_EQUITY_SERIES:
                continue
        elif seg == "BSE_EQ":
            if typ in BSE_NON_EQUITY_GROUPS or not isin.startswith("INE"):
                continue
        else:
            continue
        out.append(InstrumentRow(
            instrument_key=x["instrument_key"],
            exchange=x["exchange"],
            symbol=x["trading_symbol"],
            name=x.get("name"),
            isin=isin,
            series=typ,
        ))
    return out


def fetch() -> list[InstrumentRow]:
    raw = cached_download(URL, "upstox_complete.json.gz", max_age_s=12 * 3600)
    return parse(json.loads(gzip.decompress(raw)))

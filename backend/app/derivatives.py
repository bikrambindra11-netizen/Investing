"""Futures & options: which stocks have them, and what the option chain shows (PCR, max pain, IV,
OI walls, expected move). Facts only; no position suggestions."""
import gzip
import json
from datetime import date, datetime

from backend.sources.http import cached_download
from backend.sources import upstox_bulk
from backend.sources.upstox_instruments import URL as INSTRUMENTS_URL


def fno_universe() -> dict[str, dict]:
    """{underlying instrument key: {symbol, lot_size, expiries}} for stocks with F&O on NSE."""
    raw = cached_download(INSTRUMENTS_URL, "upstox_complete.json.gz", max_age_s=12 * 3600)
    out: dict[str, dict] = {}
    for x in json.loads(gzip.decompress(raw)):
        if x.get("segment") != "NSE_FO" or x.get("underlying_type") != "EQUITY":
            continue
        u = out.setdefault(x["underlying_key"], {"symbol": x["underlying_symbol"], "lot_size": x["lot_size"],
                                                 "expiries": set(), "has_options": False})
        u["expiries"].add(datetime.fromtimestamp(x["expiry"] / 1000).date().isoformat())
        if x["instrument_type"] in ("CE", "PE"):
            u["has_options"] = True
    for u in out.values():
        u["expiries"] = sorted(u["expiries"])
    return out


def option_chain(underlying_key: str, expiry: str) -> list[dict]:
    with upstox_bulk._client() as c:
        return upstox_bulk._get(c, "/option/chain", {"instrument_key": underlying_key, "expiry_date": expiry}) or []


def read_chain(chain: list[dict]) -> dict:
    """PCR, max pain, ATM implied volatility, and the strikes with the most open interest."""
    if not chain:
        return {"available": False}
    spot = chain[0]["underlying_spot_price"]
    rows = []
    for r in chain:
        ce, pe = r.get("call_options") or {}, r.get("put_options") or {}
        cm, pm = ce.get("market_data") or {}, pe.get("market_data") or {}
        rows.append({"strike": r["strike_price"], "ce": cm, "pe": pm, "ce_g": ce.get("option_greeks") or {},
                     "pe_g": pe.get("option_greeks") or {}, "ce_key": ce.get("instrument_key"), "pe_key": pe.get("instrument_key")})
    rows.sort(key=lambda r: r["strike"])
    call_oi = sum(r["ce"].get("oi") or 0 for r in rows)
    put_oi = sum(r["pe"].get("oi") or 0 for r in rows)
    call_doi = sum((r["ce"].get("oi") or 0) - (r["ce"].get("prev_oi") or 0) for r in rows)
    put_doi = sum((r["pe"].get("oi") or 0) - (r["pe"].get("prev_oi") or 0) for r in rows)
    # Max pain: the expiry price at which option buyers in total lose the most
    pain = []
    for k in (r["strike"] for r in rows):
        loss = sum(max(k - r["strike"], 0) * (r["ce"].get("oi") or 0) + max(r["strike"] - k, 0) * (r["pe"].get("oi") or 0) for r in rows)
        pain.append((loss, k))
    atm = min(rows, key=lambda r: abs(r["strike"] - spot))
    ivs = [x for x in (atm["ce_g"].get("iv"), atm["pe_g"].get("iv")) if x]
    call_wall = max(rows, key=lambda r: r["ce"].get("oi") or 0)
    put_wall = max(rows, key=lambda r: r["pe"].get("oi") or 0)
    pcr = round(put_oi / call_oi, 2) if call_oi else None
    reading = []
    if pcr is not None:
        reading.append(f"Put/call open-interest ratio {pcr}.")
    reading.append(f"Most call open interest at the ₹{call_wall['strike']:g} strike; most put open interest at ₹{put_wall['strike']:g}.")
    if call_doi or put_doi:
        reading.append(f"Change in open interest since the previous day: calls {call_doi:+,.0f}, puts {put_doi:+,.0f}.")
    return {"available": True, "spot": spot, "expiry": chain[0]["expiry"], "pcr": pcr, "max_pain": min(pain)[1],
            "atm_strike": atm["strike"], "atm_iv": round(sum(ivs) / len(ivs), 1) if ivs else None,
            "call_wall": call_wall["strike"], "put_wall": put_wall["strike"],
            "call_oi_change": call_doi, "put_oi_change": put_doi, "reading": reading, "rows": rows}


def pick_expiry(expiries: list[str], today: date, min_days: int = 10) -> str | None:
    future = [e for e in expiries if (date.fromisoformat(e) - today).days >= min_days]
    return future[0] if future else (expiries[-1] if expiries else None)


def positioning(symbol: str, lot: int | None, tech: dict, chain: dict, today: date | None = None) -> dict:
    """Key levels and what the options market is pricing in. Facts, no recommendation."""
    out = {"levels": {}, "facts": [],
           "label": "Facts about price levels and option positioning. Read them with the whole analysis; they are not a signal on their own."}
    if tech.get("available"):
        out["levels"].update({"supports": [l["level"] for l in tech["supports"]], "resistances": [l["level"] for l in tech["resistances"]],
                              "pivots": tech["pivots"], "atr": tech["atr14"], "atr_pct": tech["atr_pct"]})
    if chain.get("available"):
        out["levels"].update({"max_pain": chain["max_pain"], "call_oi_wall": chain["call_wall"], "put_oi_wall": chain["put_wall"]})
        days = max((date.fromisoformat(chain["expiry"]) - (today or date.today())).days, 1)
        if chain.get("atm_iv"):
            move = chain["spot"] * chain["atm_iv"] / 100 * (days / 365) ** 0.5
            out["expected_move"] = {"amount": round(move, 2), "pct": round(move / chain["spot"] * 100, 1), "days": days,
                                    "low": round(chain["spot"] - move, 2), "high": round(chain["spot"] + move, 2), "expiry": chain["expiry"]}
            out["facts"].append(f"Option prices imply a typical move of ±₹{move:,.2f} (±{move / chain['spot'] * 100:.1f}%) by expiry on {chain['expiry']}, "
                                f"a range of about ₹{chain['spot'] - move:,.2f} – ₹{chain['spot'] + move:,.2f}.")
        out["facts"] += chain["reading"]
        out["facts"].append(f"Max pain ₹{chain['max_pain']:,.0f}: the expiry price at which option buyers as a group would lose most.")
        if lot:
            out["facts"].append(f"Lot size {lot:,} shares.")
    return out


def news_score(items: list[dict]) -> float:
    if not items:
        return 0.0
    v = sum(1 if n["sentiment"] == "positive" else -1 if n["sentiment"] == "negative" else 0 for n in items[:10])
    return max(-1.0, min(1.0, v / 5))


def futures_quote(underlying_key: str, today: date) -> dict:
    """Nearest-month futures price and its premium/discount to the stock."""
    raw = cached_download(INSTRUMENTS_URL, "upstox_complete.json.gz", max_age_s=12 * 3600)
    futs = [x for x in json.loads(gzip.decompress(raw)) if x.get("segment") == "NSE_FO" and x.get("instrument_type") == "FUT"
            and x.get("underlying_key") == underlying_key]
    futs = [f for f in futs if datetime.fromtimestamp(f["expiry"] / 1000).date() >= today]
    if not futs:
        return {"available": False}
    futs.sort(key=lambda f: f["expiry"])
    keys = [f["instrument_key"] for f in futs[:2]] + [underlying_key]
    px = upstox_bulk.last_prices(keys)
    spot = px.get(underlying_key)
    out = []
    for f in futs[:2]:
        p = px.get(f["instrument_key"])
        exp = datetime.fromtimestamp(f["expiry"] / 1000).date()
        if p and spot:
            out.append({"expiry": exp.isoformat(), "price": p, "basis": round(p - spot, 2), "basis_pct": round((p / spot - 1) * 100, 2),
                        "lot_size": f["lot_size"]})
    return {"available": bool(out), "spot": spot, "contracts": out}


def strikes_that_matter(chain: dict, tech: dict, struct: dict, pos: dict) -> list[dict]:
    """Option strikes sitting at the levels that matter, with their market data. Information only."""
    if not chain.get("available"):
        return []
    rows = {r["strike"]: r for r in chain["rows"]}
    strikes = sorted(rows)
    refs = []
    for l in tech.get("supports", []):
        refs.append((l["level"], f"support ₹{l['level']:,.2f}"))
    for l in tech.get("resistances", []):
        refs.append((l["level"], f"resistance ₹{l['level']:,.2f}"))
    fib = (struct or {}).get("fibonacci")
    if fib:
        for lv in fib["levels"]:
            refs.append((lv["price"], f"Fibonacci {lv['ratio']} at ₹{lv['price']:,.2f}"))
    em = pos.get("expected_move")
    if em:
        refs += [(em["low"], f"lower edge of expected range ₹{em['low']:,.2f}"), (em["high"], f"upper edge of expected range ₹{em['high']:,.2f}")]
    refs += [(chain["call_wall"], "most call open interest"), (chain["put_wall"], "most put open interest"),
             (chain["atm_strike"], "at the money")]
    picked: dict[float, list[str]] = {}
    for level, why in refs:
        k = min(strikes, key=lambda s: abs(s - level))
        if abs(k / level - 1) <= 0.03:
            picked.setdefault(k, []).append(why)
    out = []
    for k in sorted(picked):
        r = rows[k]
        ce, pe, cg, pg = r["ce"], r["pe"], r["ce_g"], r["pe_g"]
        out.append({"strike": k, "why": sorted(set(picked[k])), "expiry": chain["expiry"],
                    "call": {"ltp": ce.get("ltp"), "oi": ce.get("oi"), "oi_change": (ce.get("oi") or 0) - (ce.get("prev_oi") or 0),
                             "iv": cg.get("iv"), "delta": cg.get("delta"), "theta": cg.get("theta"),
                             "breakeven": round(k + ce["ltp"], 2) if ce.get("ltp") else None},
                    "put": {"ltp": pe.get("ltp"), "oi": pe.get("oi"), "oi_change": (pe.get("oi") or 0) - (pe.get("prev_oi") or 0),
                            "iv": pg.get("iv"), "delta": pg.get("delta"), "theta": pg.get("theta"),
                            "breakeven": round(k - pe["ltp"], 2) if pe.get("ltp") else None}})
    return out

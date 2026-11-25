"""Futures & options: which stocks have them, option-chain reading (PCR, max pain, IV, OI walls),
and a trade idea that combines the chart, news, fundamentals and the option chain."""
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
        reading.append(f"Put/call ratio {pcr}: " + ("more puts written than calls, traders expect support (bullish tilt)." if pcr > 1.2
                        else "more calls written than puts, traders expect a ceiling (bearish tilt)." if pcr < 0.7 else "balanced."))
    reading.append(f"Biggest call open interest at ₹{call_wall['strike']:g} (acts as resistance); biggest put open interest at ₹{put_wall['strike']:g} (acts as support).")
    if call_doi or put_doi:
        reading.append(f"Today's change in open interest: calls {call_doi:+,.0f}, puts {put_doi:+,.0f}" +
                       (" — put writing, a bullish sign." if put_doi > call_doi > 0 or (put_doi > 0 >= call_doi) else
                        " — call writing, a bearish sign." if call_doi > put_doi > 0 or (call_doi > 0 >= put_doi) else "."))
    return {"available": True, "spot": spot, "expiry": chain[0]["expiry"], "pcr": pcr, "max_pain": min(pain)[1],
            "atm_strike": atm["strike"], "atm_iv": round(sum(ivs) / len(ivs), 1) if ivs else None,
            "call_wall": call_wall["strike"], "put_wall": put_wall["strike"],
            "call_oi_change": call_doi, "put_oi_change": put_doi, "reading": reading, "rows": rows}


def pick_expiry(expiries: list[str], today: date, min_days: int = 10) -> str | None:
    future = [e for e in expiries if (date.fromisoformat(e) - today).days >= min_days]
    return future[0] if future else (expiries[-1] if expiries else None)


def trade_idea(symbol: str, lot: int, tech: dict, chain: dict, news_score: float, fund_grade: str | None,
               macro_share: float | None) -> dict:
    """A setup view: how the chart, the option chain, news, fundamentals and the economy line up, with
    the key levels and scenarios. It describes the situation; it does not pick a position."""
    parts = []
    t = tech.get("score", 0) if tech.get("available") else 0
    parts.append(("Chart", t, tech.get("summary", "not available")))
    if chain.get("available"):
        o = 0.0
        if chain["pcr"] is not None:
            o += 0.5 if chain["pcr"] > 1.2 else -0.5 if chain["pcr"] < 0.7 else 0
        if chain["put_oi_change"] > max(chain["call_oi_change"], 0):
            o += 0.5
        elif chain["call_oi_change"] > max(chain["put_oi_change"], 0):
            o -= 0.5
        parts.append(("Option chain", o, " ".join(chain["reading"][:1])))
    parts.append(("News", news_score, "tone of recent headlines"))
    f = {"A": 0.6, "B": 0.3, "C": 0, "D": -0.3, "E": -0.6}.get(fund_grade or "", 0)
    parts.append(("Fundamentals", f, f"rating {fund_grade}" if fund_grade else "not rated in this view"))
    m = 0 if macro_share is None else (macro_share - 0.5)
    parts.append(("Economy", m, "share of industry drivers that are tailwinds"))
    weights = {"Chart": 0.4, "Option chain": 0.2, "News": 0.15, "Fundamentals": 0.15, "Economy": 0.1}
    score = sum(weights[n] * v for n, v, _ in parts) / sum(weights[n] for n, _, _ in parts)
    lean = "bullish" if score >= 0.2 else "bearish" if score <= -0.2 else "no clear edge"
    agree = [n for n, v, _ in parts if (v > 0.1 and score > 0) or (v < -0.1 and score < 0)]
    disagree = [n for n, v, _ in parts if (v > 0.1 and score < 0) or (v < -0.1 and score > 0)]

    sup = [l["level"] for l in (tech.get("supports") or [])] if tech.get("available") else []
    res = [l["level"] for l in (tech.get("resistances") or [])] if tech.get("available") else []
    levels = {"supports": sup, "resistances": res,
              "pivots": tech.get("pivots") if tech.get("available") else None,
              "atr": tech.get("atr14"), "atr_pct": tech.get("atr_pct")}
    if chain.get("available"):
        levels.update({"max_pain": chain["max_pain"], "call_oi_wall": chain["call_wall"], "put_oi_wall": chain["put_wall"]})
    scenarios = []
    if sup:
        scenarios.append(f"If {symbol} holds above support ₹{sup[0]:,.2f}, the setup stays intact; a close below it would weaken the picture"
                         + (f", with the next support near ₹{sup[1]:,.2f}." if len(sup) > 1 else "."))
    if res:
        scenarios.append(f"Resistance is at ₹{res[0]:,.2f}; a close above it on good volume would be a breakout"
                         + (f", with the next resistance near ₹{res[1]:,.2f}." if len(res) > 1 else "."))
    if tech.get("atr14"):
        scenarios.append(f"A normal day's move is about ₹{tech['atr14']:,.2f} ({tech['atr_pct']}%): moves smaller than that are noise.")
    option_facts = []
    if chain.get("available"):
        option_facts = list(chain["reading"]) + [
            f"At-the-money implied volatility {chain['atm_iv']}%" + (" — high, so options are expensive." if (chain["atm_iv"] or 0) > 40 else "."),
            f"Max pain ₹{chain['max_pain']:,.0f}: the price where option buyers as a group lose most at expiry ({chain['expiry']}).",
            f"Lot size {lot:,} shares." if lot else ""]
        option_facts = [x for x in option_facts if x]
    return {"score": round(score, 2), "lean": lean, "direction": "up" if lean == "bullish" else "down" if lean == "bearish" else None,
            "view": f"{symbol}: signals lean {lean}." if lean != "no clear edge" else f"{symbol}: no clear edge; the signals disagree.",
            "agree": agree, "disagree": disagree,
            "evidence": [{"factor": n, "score": round(v, 2), "note": note} for n, v, note in parts],
            "levels": levels, "scenarios": scenarios, "option_facts": option_facts,
            "label": "Analysis only, not a recommendation. Decide positions and sizes yourself."}


def news_score(items: list[dict]) -> float:
    if not items:
        return 0.0
    v = sum(1 if n["sentiment"] == "positive" else -1 if n["sentiment"] == "negative" else 0 for n in items[:10])
    return max(-1.0, min(1.0, v / 5))

"""Builds the stock page and industry page payloads."""
import re
from datetime import timedelta

from sqlalchemy import select

from backend.sources import cache, news, nse_sectors, upstox_candles, upstox_fundamentals

from . import analysis, macro
from .db import Instrument, SessionLocal
from .jobs import current_token, today_ist
from .live import live
from .market_data import build_rows

NEWS_TTL = timedelta(minutes=20)


def _clean_name(name: str) -> str:
    n = re.sub(r"\b(ltd|limited|ltd\.|the|co|corp|corporation|inc|plc)\b\.?", "", name, flags=re.I)
    return re.sub(r"\s+", " ", n.replace(".", " ")).strip().title()


def company_news(name: str) -> dict:
    q = f'"{_clean_name(name)}" share OR stock OR results'
    try:
        items, at = cache.get_or_fetch(f"news:{q}", news.SOURCE, NEWS_TTL, lambda: news.search(q))
        return {"items": items, "fetched_at": at.isoformat(), "source": news.SOURCE, "query": q}
    except Exception as e:
        return {"items": [], "error": str(e), "source": news.SOURCE}


def industry_news(label: str) -> dict:
    q = f"{label} sector India stocks"
    try:
        items, at = cache.get_or_fetch(f"news:{q}", news.SOURCE, NEWS_TTL, lambda: news.search(q))
        return {"items": items, "fetched_at": at.isoformat(), "source": news.SOURCE, "query": q}
    except Exception as e:
        return {"items": [], "error": str(e), "source": news.SOURCE}


def _rows_by_isin(rows: list[dict]) -> dict[str, dict]:
    return {r["isin"]: r for r in rows if r.get("isin")}


def _peer_row(r: dict, f_ratios: dict | None) -> dict:
    kr = analysis.key_ratios({"ratios": f_ratios}) if f_ratios else {}
    return {"isin": r["isin"], "symbol": r["symbol"], "name": r["name"], "key": r["key"],
            "close": r["close"], "change_pct": r["change_pct"], "turnover": r["turnover"],
            "price_date": r["price_date"], "sector": r.get("sector"),
            "pe": (kr.get("P/E") or {}).get("company"), "pb": (kr.get("P/B") or {}).get("company"),
            "roe": (kr.get("ROE") or {}).get("company"), "roce": (kr.get("ROCE") or {}).get("company"),
            "ev_ebitda": (kr.get("EV/EBITDA") or {}).get("company"),
            "ratios_fetched_at": f_ratios.get("fetched_at") if f_ratios else None}


def _cached_ratios(isin: str, token: str | None) -> dict | None:
    """Key ratios for a peer: from cache, or fetched when logged in."""
    hit = cache.get(f"fund:{isin}:ratios", None)
    if hit:
        return {"data": hit[0], "fetched_at": hit[1].isoformat()}
    if not token:
        return None
    try:
        data, at = cache.get_or_fetch(f"fund:{isin}:ratios", upstox_fundamentals.SOURCE, timedelta(days=7),
                                      lambda: upstox_fundamentals._get(isin, "key-ratios", {}, token))
        return {"data": data, "fetched_at": at.isoformat()}
    except Exception:
        return None


def stock_page(isin: str) -> dict | None:
    with SessionLocal() as s:
        listings = s.scalars(select(Instrument).where(Instrument.isin == isin)).all()
        if not listings:
            return None
        listings = sorted(listings, key=lambda i: i.exchange != "NSE")
        primary = listings[0]
        info = {"isin": isin, "name": primary.name, "symbol": primary.symbol, "key": primary.instrument_key,
                "listings": [{"exchange": i.exchange, "symbol": i.symbol, "key": i.instrument_key, "series": i.series}
                             for i in listings],
                "nse_sector": next((i.sector for i in listings if i.sector), None)}
        rows, as_of = build_rows(s)
    row = _rows_by_isin(rows).get(isin, {})
    token = current_token()

    # Price history (no login needed)
    try:
        candles, c_at = upstox_candles.daily(primary.instrument_key, today_ist(), token)
        candles_err = None
    except Exception as e:
        candles, c_at, candles_err = [], None, str(e)
    stats = analysis.price_stats(candles)
    tick = live.since(0)[1].get(primary.instrument_key)
    price = tick["ltp"] if tick else (row.get("close") or stats.get("close"))

    # Company fundamentals (need the Upstox login; cached copies are used when logged out)
    f = upstox_fundamentals.fetch_all(isin, token)
    profile = (f.get("profile") or {}).get("data") or {}
    upstox_sector = profile.get("sector")
    industry_id = macro.resolve_industry(upstox_sector, primary.name, info["nse_sector"])
    ind_cfg = macro.load_industries()[industry_id]
    have_fund = bool((f.get("income") or {}).get("data"))
    needs_login = any((v or {}).get("error") == "needs_login" for v in f.values())

    classification = {
        "macro_economic_sector": nse_sectors.SECTOR_TO_MACRO.get(info["nse_sector"]) if info["nse_sector"] else None,
        "sector": info["nse_sector"],
        "industry": ind_cfg["label"],
        "basic_industry": upstox_sector,
        "sources": {"sector": nse_sectors.SOURCE if info["nse_sector"] else None,
                    "basic_industry": upstox_fundamentals.SOURCE if upstox_sector else None,
                    "industry": "Portal industry map (industry_drivers.yaml)"},
        "industry_id": industry_id,
    }

    macro_panel = macro.industry_macro(industry_id)
    fin = analysis.financials(f) if have_fund else None
    kr = analysis.key_ratios(f)
    holdings = analysis.shareholding(f) if (f.get("holdings") or {}).get("data") else None
    val = analysis.valuation(industry_id, f, fin, candles, price) if fin else None
    g = analysis.graham(industry_id, fin, f, price) if fin else None
    qual = analysis.quality(industry_id, fin, kr) if fin else None
    capital = analysis.capital_allocation(f, fin) if fin else None
    risk = analysis.risks(industry_id, fin, kr, holdings or {}, stats, macro_panel, val or {}) if fin else \
        analysis.risks(industry_id, {"periods": []}, kr, {}, stats, macro_panel, {})

    # Peers: Upstox competitors first, then same-industry stocks by turnover.
    by_isin = _rows_by_isin(rows)
    peer_isins = []
    for c in (f.get("competitors") or {}).get("data") or []:
        pi = (c.get("instrument_key") or "").split("|")[-1]
        if pi in by_isin and pi != isin:
            peer_isins.append(pi)
    same = [r for r in rows if r.get("industry") == industry_id and r["isin"] != isin
            and (info["nse_sector"] is None or r.get("sector") == info["nse_sector"] or industry_id in ("banks", "nbfc"))]
    for r in same:
        if len(peer_isins) >= 10:
            break
        if r["isin"] not in peer_isins:
            peer_isins.append(r["isin"])
    peers = [_peer_row(row, _cached_ratios(isin, token)) if row else None] if row else []
    peers += [_peer_row(by_isin[p], _cached_ratios(p, token)) for p in peer_isins]

    return {
        "info": info,
        "quote": {**{k: row.get(k) for k in ("close", "prev_close", "change_pct", "volume", "turnover",
                                              "price_date", "price_source")},
                  "live": {"ltp": tick["ltp"], "cp": tick["cp"], "ltt": tick["ltt"].isoformat() if tick["ltt"] else None}
                  if tick else None},
        "candles": candles,
        "candles_meta": {"source": upstox_candles.SOURCE, "fetched_at": c_at.isoformat() if c_at else None,
                         "error": candles_err},
        "stats": stats,
        "classification": classification,
        "profile": {"description": profile.get("company_profile"),
                    "market_cap_cr": (profile.get("sector_market_cap_inr") or {}).get("value"),
                    "fetched_at": (f.get("profile") or {}).get("fetched_at")},
        "fundamentals_status": {"available": have_fund, "needs_login": needs_login and not have_fund,
                                "errors": {k: v.get("detail") for k, v in f.items() if v.get("error") == "failed"},
                                "source": upstox_fundamentals.SOURCE},
        "financials": fin,
        "quality": qual,
        "capital_allocation": capital,
        "shareholding": holdings,
        "valuation": val,
        "graham": g,
        "risks": risk,
        "macro": macro_panel,
        "peers": peers,
        "news": company_news(primary.name or primary.symbol),
        "summary": analysis.summary(primary.name or primary.symbol, macro_panel, qual, g, val, stats),
        "as_of": as_of,
    }


def industries_list() -> list[dict]:
    with SessionLocal() as s:
        rows, _ = build_rows(s)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["industry"]] = counts.get(r["industry"], 0) + 1
    out = []
    for iid, ind in macro.load_industries().items():
        m = macro.industry_macro(iid)
        out.append({"id": iid, "label": ind["label"], "stocks": counts.get(iid, 0), "score": m["score"]})
    return out


def industry_page(industry_id: str) -> dict | None:
    inds = macro.load_industries()
    if industry_id not in inds:
        return None
    with SessionLocal() as s:
        rows, as_of = build_rows(s)
    token = current_token()
    members = [r for r in rows if r.get("industry") == industry_id]
    members.sort(key=lambda r: -(r["turnover"] or 0))
    peers = [_peer_row(r, _cached_ratios(r["isin"], token) if i < 15 else
                       ({"data": cache.get(f"fund:{r['isin']}:ratios", None)[0]} if cache.get(f"fund:{r['isin']}:ratios", None) else None))
             for i, r in enumerate(members[:60])]
    return {"id": industry_id, "label": inds[industry_id]["label"], "macro": macro.industry_macro(industry_id),
            "peers": peers, "total_members": len(members), "news": industry_news(inds[industry_id]["label"]),
            "as_of": as_of,
            "membership_note": "Companies are placed in an industry using NSE sector lists and company names; "
                               "after the Upstox login, each company's own detailed sector refines this on its stock page."}

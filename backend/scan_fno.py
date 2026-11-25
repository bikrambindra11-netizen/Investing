"""Scan every stock that has futures & options for trade setups right now.

Usage: python -m backend.scan_fno OUT.json
For each F&O stock: chart (technicals), live price, option chain, and key ratios. The strongest
setups get a news check and a full trade idea.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

os.environ.setdefault("RUN_JOBS", "false")
os.environ.setdefault("UPSTOX_ACCESS_TOKEN", "proxy-injected")

from backend.app import derivatives, jobs, technicals  # noqa: E402
from backend.app.stock import company_news  # noqa: E402
from backend.app.db import init_db  # noqa: E402
from backend.sources import upstox_bulk, upstox_candles  # noqa: E402


def main() -> None:
    out_path = sys.argv[1]
    init_db()
    today = jobs.today_ist()
    uni = derivatives.fno_universe()
    keys = list(uni)
    prices = upstox_bulk.last_prices(keys)

    def tech_for(k):
        try:
            c = upstox_candles._fetch(k, today, None)
            return k, technicals.analyse(c, prices.get(k))
        except Exception as e:
            return k, {"available": False, "reason": str(e)}

    with ThreadPoolExecutor(6) as ex:
        techs = dict(ex.map(tech_for, keys))
    ranked = sorted((k for k in keys if techs[k].get("available")), key=lambda k: -abs(techs[k]["score"]))
    shortlist = ranked[:40]

    def full(k):
        u = uni[k]
        exp = derivatives.pick_expiry(u["expiries"], today)
        chain = derivatives.read_chain(derivatives.option_chain(k, exp)) if exp and u["has_options"] else {"available": False}
        name = u["symbol"]
        news = company_news(name)["items"]
        idea = derivatives.trade_idea(name, u["lot_size"], techs[k], chain, derivatives.news_score(news), None, None)
        return {"symbol": name, "instrument_key": k, "isin": k.split("|")[-1], "price": prices.get(k),
                "technical_bias": techs[k]["bias"], "technical_score": techs[k]["score"],
                "rsi": techs[k]["rsi14"], "supports": [l["level"] for l in techs[k]["supports"]],
                "resistances": [l["level"] for l in techs[k]["resistances"]],
                "signals": [s["text"] for s in techs[k]["signals"]][:5],
                "option_chain": {x: chain.get(x) for x in ("pcr", "max_pain", "atm_iv", "call_wall", "put_wall", "expiry", "reading")},
                "headlines": [{"title": n["title"], "sentiment": n["sentiment"], "link": n["link"]} for n in news[:3]],
                "idea": idea}

    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(full, shortlist))
    ideas = [r for r in results if r["idea"].get("option")]
    ideas.sort(key=lambda r: -abs(r["idea"]["score"]))
    overview = [{"symbol": uni[k]["symbol"], "isin": k.split("|")[-1], "price": prices.get(k), "bias": techs[k]["bias"],
                 "score": techs[k]["score"], "rsi": techs[k]["rsi14"]} for k in ranked]
    result = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "universe": len(keys),
              "scanned": len(ranked), "ideas": ideas[:15], "no_edge": [r["symbol"] for r in results if not r["idea"].get("option")],
              "overview": overview,
              "label": "Trade ideas from rules, not advice. Options can lose 100% of the premium."}
    with open(out_path, "w") as fh:
        json.dump(result, fh, default=str)
    with open(out_path + ".db.json", "w") as fh:  # fields for the page's scans/latest document
        json.dump({"status": "done", "step": "", "updated_at": result["generated_at"], "scan": result}, fh, default=str)
    print(f"wrote {out_path}: {len(ranked)} stocks scanned, {len(ideas)} with a trade idea, "
          f"{os.path.getsize(out_path) // 1024} KB")


if __name__ == "__main__":
    main()

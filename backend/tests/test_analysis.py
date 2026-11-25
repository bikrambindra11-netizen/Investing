"""Company analysis, tested on Upstox's documented sample responses (Reliance Industries)."""
import json
from pathlib import Path

import pytest

from backend.app import analysis as a

FIX = Path(__file__).parent / "fixtures"
NAMES = ["profile", "income", "balance", "cashflow", "ratios", "holdings", "actions", "competitors"]


@pytest.fixture
def f():
    return {k: {"data": json.loads((FIX / f"upstox_{k}.json").read_text()), "fetched_at": "2026-11-25T00:00:00"}
            for k in NAMES}


def candles(price=1300.0):
    return [{"date": f"{y}-{m:02d}-28", "open": price, "high": price * 1.1, "low": price * 0.9, "close": price,
             "volume": 1000} for y in range(2016, 2027) for m in range(1, 13)]


def test_period_end_and_cagr():
    assert str(a.period_end("Mar 2025")) == "2025-03-31"
    assert str(a.period_end("Dec 2024")) == "2024-12-31"
    assert a.period_end("FY25") is None
    assert a.cagr(200, 100, 5) == 14.9
    assert a.cagr(100, -5, 3) is None  # no growth rate from a loss


def test_eps_adjusted_for_bonus(f):
    fin = a.financials(f)
    eps = {r["period"]: r["eps"] for r in fin["periods"]}
    # Reliance's 1:1 bonus in 2023: raw EPS 98.59 restated to about half
    assert fin["eps_adjustments"][0]["between"] == "Mar 2023 and Mar 2024"
    assert eps["Mar 2023"] == pytest.approx(48.2, abs=0.1)
    assert eps["Mar 2025"] == 51.47


def test_financial_history(f):
    fin = a.financials(f)
    latest = fin["periods"][0]
    assert latest["period"] == "Mar 2026" and latest["revenue"] == 1086181 and latest["net_profit"] == 95610
    y25 = next(r for r in fin["periods"] if r["period"] == "Mar 2025")
    assert y25["net_margin_pct"] == pytest.approx(80787 / 982671 * 100, abs=0.1)
    assert y25["roe_pct"] == pytest.approx(80787 / 1009626 * 100, abs=0.1)
    assert y25["cfo_to_profit"] == pytest.approx(178703 / 80787, abs=0.01)
    assert y25["current_ratio"] == pytest.approx(499270 / 453737, abs=0.01)
    assert fin["growth"]["revenue_cagr_pct"] is not None


def test_graham_checks(f):
    fin = a.financials(f)
    checks = {c["name"]: c for c in a.graham("oil_gas", fin, f, 1351.0)}
    assert checks["Adequate size"]["status"] == "pass"
    assert checks["Strong financial condition"]["status"] == "fail"  # current ratio ~1.1
    assert checks["Earnings stability"]["status"] == "partial"  # profitable, but < 10 years of data
    assert checks["Earnings growth"]["status"] == "not_available"  # needs 6+ years of EPS
    assert checks["Moderate P/E"]["status"] == "fail"
    assert "Mar 2025" in checks["Moderate price to book"]["value"]


def test_banks_skip_current_ratio(f):
    fin = a.financials(f)
    check = next(c for c in a.graham("banks", fin, f, 1351.0) if c["name"] == "Strong financial condition")
    assert check["status"] == "skipped" and "banks" in check["note"]


def test_valuation_metrics_by_industry(f):
    fin = a.financials(f)
    assert a.valuation("banks", f, fin, candles(), 1351.0)["chosen"] == ["P/B", "P/E"]
    assert a.valuation("metals", f, fin, candles(), 1351.0)["chosen"] == ["EV/EBITDA", "P/B"]
    v = a.valuation("it", f, fin, candles(), 1351.0)
    assert v["chosen"] == ["P/E", "EV/EBITDA"]
    pe = v["metrics"][0]
    assert pe["current"] == 20.15 and pe["sector"] == 12.46 and pe["vs_sector_pct"] == 62
    assert v["label"] in {"expensive", "fair"}


def test_missing_data_is_not_guessed():
    empty = {k: {"error": "needs_login"} for k in NAMES}
    fin = a.financials(empty)
    assert fin["periods"] == [] and fin["growth"] == {}
    assert all(c["status"] in ("not_available", "skipped") for c in a.graham("it", fin, empty, None))


def test_price_stats():
    c = candles(100.0)
    c[-1] = {**c[-1], "close": 120.0}
    s = a.price_stats(c)
    assert s["close"] == 120.0 and s["return_1y"] == 20.0 and s["high_52w"] == pytest.approx(110.0)


def test_summary_without_financials():
    macro = {"label": "IT services", "score": {"tailwinds": 2, "headwinds": 1, "judged": 3, "share_tailwinds": 0.67},
             "drivers": []}
    s = a.summary("TCS", macro, None, None, None, {"available": False})
    assert "Upstox login" in s["verdict"] and s["label"].startswith("Screening output")

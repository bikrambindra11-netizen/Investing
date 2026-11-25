from backend.app import derivatives, technicals


def bar(d, o, h, l, c, v=1000):
    return {"date": f"2026-{d // 28 + 1:02d}-{d % 28 + 1:02d}", "open": o, "high": h, "low": l, "close": c, "volume": v}


def series(prices):
    return [bar(i, p, p * 1.01, p * 0.99, p) for i, p in enumerate(prices)]


def test_rsi_extremes_and_sma():
    up = [100 + i for i in range(40)]
    assert technicals.rsi(up) == 100.0
    assert technicals.sma([1, 2, 3, 4], 2) == 3.5


def test_fibonacci_after_a_rise():
    c = series([100 + i for i in range(50)] + [149 - i for i in range(10)])  # up to ~149, then back
    f = technicals.fibonacci(c, lookback=60)
    assert f["direction"] == "up"
    half = next(l["price"] for l in f["levels"] if l["ratio"] == 0.5)
    assert abs(half - (f["from"]["price"] + f["to"]["price"]) / 2) < 0.01
    assert 0 < f["retraced_pct"] < 30


def test_engulfing_and_hammer_detected():
    c = series([100 - i for i in range(10)])  # falling
    c.append(bar(10, 90.5, 90.6, 89.4, 89.5))  # small red
    c.append(bar(11, 89.3, 91.5, 89.2, 91.2))  # big green engulfing
    c.append(bar(12, 91.0, 91.1, 87.0, 90.8))  # long lower wick
    names = {p["pattern"] for p in technicals.candle_patterns(c, last=5)}
    assert "Bullish engulfing" in names


def test_rising_trend_line_found():
    import math
    prices = [100 + i * 0.5 + 5 * math.sin(i / 3) for i in range(120)]
    c = [bar(i, p, p + 1, p - 1, p) for i, p in enumerate(prices)]
    tl = technicals.trend_lines(c)
    assert any(t["kind"] == "rising support" and t["slope_per_day"] > 0 for t in tl)


def test_levels_and_structure_have_no_buy_sell_words():
    import math
    prices = [100 + 10 * math.sin(i / 8) for i in range(260)]
    c = [bar(i, p, p + 1, p - 1, p, 1000 + i) for i, p in enumerate(prices)]
    t = technicals.analyse(c)
    text = " ".join(t["observations"]).lower()
    assert "bullish" not in text and "bearish" not in text and "buy" not in text
    assert t["supports"] or t["resistances"]


def test_strikes_at_levels():
    chain = {"available": True, "expiry": "2026-12-29", "spot": 100, "atm_strike": 100, "call_wall": 110, "put_wall": 90,
             "rows": [{"strike": k, "ce": {"ltp": max(100 - k, 0) + 2, "oi": 10, "prev_oi": 5}, "pe": {"ltp": max(k - 100, 0) + 2, "oi": 8, "prev_oi": 8},
                       "ce_g": {"delta": 0.5, "iv": 30}, "pe_g": {"delta": -0.5, "iv": 31}} for k in range(80, 125, 5)]}
    tech = {"supports": [{"level": 94.8}], "resistances": [{"level": 105.2}]}
    rows = derivatives.strikes_that_matter(chain, tech, {}, {})
    ks = {r["strike"]: r for r in rows}
    assert {95, 105, 100, 110, 90} <= set(ks)
    assert ks[105]["call"]["breakeven"] == 107 and ks[95]["put"]["breakeven"] == 93

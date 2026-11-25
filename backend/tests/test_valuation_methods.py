from backend.app import valuation_methods as vm


def fin(eps, pat, margins, growth=10.0):
    periods = [{"period": f"Mar {2026 - i}", "eps": e, "net_profit": p, "operating_profit": m * 10, "revenue": 1000.0,
                "operating_margin_pct": m, "roe_pct": 15.0} for i, (e, p, m) in enumerate(zip(eps, pat, margins))]
    return {"periods": periods, "growth": {"net_profit_cagr_pct": growth, "years": 3}}


KR = {"P/E": {"company": 20.0, "sector": 25.0}, "P/B": {"company": 2.0, "sector": 3.0}, "ROE": {"company": 15.0},
      "EV/EBITDA": {"company": 10.0, "sector": 12.0}}


def test_every_industry_has_known_methods():
    cfg = vm.load()
    for iid, ind in cfg["industries"].items():
        for m in ind["primary"] + ind.get("secondary", []):
            assert m in vm.METHODS, (iid, m)
        for s in ind.get("sources", []):
            assert s in cfg["sources"], (iid, s)


def test_banks_use_book_value_not_pe():
    g = vm.guide("banks")
    assert [m["id"] for m in g["primary"]] == ["pb_roe", "residual_income"]
    assert any("EV/EBITDA" in a["method"] for a in g["avoid"])


def test_justified_pb():
    r = vm.assess("banks", fin([10, 9, 8], [100, 90, 80], [30, 30, 30]), KR, 200.0)
    pb = next(m for m in r["methods"] if m["id"] == "pb_roe")
    # ROE 15, long-run g 5, ke 12.5 -> (15-5)/(12.5-5) = 1.33x book; book = 200/2 = 100 -> value 133.33
    assert pb["figures"]["justified P/B"] == 1.33 and pb["value"] == 133.33
    assert pb["figures"]["ROE the price assumes %"] == 20.0


def test_reverse_dcf_matches_dcf():
    f = fin([10, 9, 8], [100, 90, 80], [20, 20, 20])
    shares = 10.0
    v = vm.earnings_dcf(100, 15, 8, shares)
    r = vm.m_reverse_dcf(vm._basics(f, KR, v), v)
    assert abs(r["figures"]["growth implied %"] - 8) < 0.2


def test_cycle_peak_detected():
    f = fin([20, 8, 5, 6], [200, 80, 50, 60], [25, 12, 8, 10])
    c = vm.cycle_position("metals", f)
    assert c["cyclical"] and c["stage"] == "near the top of its cycle"
    assert not vm.cycle_position("fmcg", f)["cyclical"]


def test_mid_cycle_multiple():
    f = fin([20, 8, 5, 6], [200, 80, 50, 60], [25, 12, 8, 10])
    m = vm.m_mid_cycle_ev_ebitda(vm._basics(f, KR, 100.0), 100.0)
    # latest op profit 250, average (250+120+80+100)/4 = 137.5 -> 10 * 250 / 137.5
    assert m["figures"]["EV/EBITDA on average profit"] == round(10 * 250 / 137.5, 1)


def test_missing_document_figure_is_not_guessed():
    r = vm.assess("cement", fin([10, 9, 8], [100, 90, 80], [20, 18, 15]), KR, 200.0)
    ev = next(m for m in r["methods"] if m["id"] == "ev_replacement")
    assert ev["available"] is False and ev["needs_document"]

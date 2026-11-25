from datetime import date

from backend.app import macro
from backend.sources import fred, mospi, news, rbi


def test_fred_csv():
    pts = fred.parse("observation_date,DGS10\n2026-11-20,4.90\n2026-11-21,.\n2026-11-23,4.92\n")
    assert pts == [("2026-11-20", 4.90), ("2026-11-23", 4.92)]


def test_rbi_rates_panel():
    page = "<div>Policy Repo Rate : 5.50%</div><p>CRR : 3.00%</p> SLR : 18.00% 91 day T-bills : 5.8846%*"
    assert rbi.parse(page) == {"repo_rate": 5.5, "crr": 3.0, "slr": 18.0, "tbill_91d": 5.8846}


def test_mospi_parsers():
    iip = mospi.parse_iip([
        {"year": 2026, "month": "September", "category": "General", "sub_category": "", "growth_rate": "6.7"},
        {"year": 2026, "month": "September", "category": "Manufacturing",
         "sub_category": "Manufacture of Basic Metals", "growth_rate": "3.1"},
    ])
    assert iip["General"] == [("2026-09-30", 6.7)]
    assert iip["Manufacturing|Manufacture of Basic Metals"] == [("2026-09-30", 3.1)]
    cpi = mospi.parse_cpi([
        {"year": "2026", "month": "October", "state": "All India", "sector": "Combined", "division": "CPI (General)",
         "group": None, "inflation": "6.09"},
        {"year": "2026", "month": "October", "state": "All India", "sector": "Rural", "division": "CPI (General)",
         "group": None, "inflation": "6.63"},
    ])
    assert cpi == {"CPI (General)": [("2026-10-31", 6.09)]}
    gdp = mospi.parse_gdp([{"year": "2026-27", "quarter": "Q1", "constant_price": "7.8"},
                           {"year": "2025-26", "quarter": "Q4", "constant_price": "8.6"}])
    assert gdp == [("2026-06-30", 7.8), ("2026-03-31", 8.6)]


def _monthly(start: float, step: float, n: int = 14):
    return [(date(2025 + (i // 12), i % 12 + 1, 28).isoformat(), start + step * i) for i in range(n)]


def test_level_verdicts():
    cfg = {"label": "Crude", "unit": "$", "kind": "level", "band_pct": 5}
    rising = macro.judge(cfg, _monthly(80, 2), good="down")
    assert rising["direction"] == "up" and rising["verdict"] == "headwind"
    assert macro.judge(cfg, _monthly(80, 2), good="up")["verdict"] == "tailwind"
    assert macro.judge(cfg, _monthly(80, 0.01), good="up")["verdict"] == "neutral"


def test_reading_verdicts():
    cfg = {"label": "CPI", "unit": "% YoY", "kind": "reading", "hi": 6, "lo": 4}
    assert macro.judge(cfg, [("2026-08-31", 7), ("2026-09-30", 7), ("2026-10-31", 7)], good="down")["verdict"] == "headwind"
    assert macro.judge(cfg, [("2026-10-31", 3)], good="down")["verdict"] == "tailwind"
    assert macro.judge(cfg, [("2026-10-31", 5)], good="down")["verdict"] == "neutral"
    assert macro.judge(cfg, [], good="down")["verdict"] == "not available"


def test_yoy_transform():
    pts = [("2025-01-31", 100.0), ("2026-01-31", 110.0)]
    assert macro.yoy(pts) == [("2026-01-31", 10.0)]


def test_industry_resolution():
    assert macro.resolve_industry(None, "HDFC BANK LTD", "Financial Services") == "banks"
    assert macro.resolve_industry(None, "BAJAJ FINANCE LIMITED", "Financial Services") == "nbfc"
    assert macro.resolve_industry(None, "TATA CONSULTANCY SERV LT", "Information Technology") == "it"
    assert macro.resolve_industry("Refineries", "RELIANCE INDUSTRIES", None) == "oil_gas"
    assert macro.resolve_industry("Cement & Cement Products", "ULTRATECH", "Construction Materials") == "cement"
    assert macro.resolve_industry(None, "UNKNOWN CO", None) == "general"


def test_config_consistency():
    series = macro.load_series()
    for iid, ind in macro.load_industries().items():
        assert ind["drivers"], iid
        for d in ind["drivers"]:
            assert d["series"] in series, (iid, d["series"])
            assert d["good"] in ("up", "down")


def test_news_sentiment_and_rss():
    assert news.sentiment("Infosys shares surge after strong results") == "positive"
    assert news.sentiment("Vedanta shares plunge on SEBI probe") == "negative"
    assert news.sentiment("Company to hold board meeting") == "neutral"
    rss = b"""<rss><channel>
      <item><title>TCS bags order from UK bank - Economic Times</title><link>https://x/1</link>
        <pubDate>Tue, 24 Nov 2026 10:00:00 GMT</pubDate><source url="https://et">Economic Times</source></item>
      <item><title>TCS shares fall - Mint</title><link>https://x/2</link>
        <pubDate>Wed, 25 Nov 2026 10:00:00 GMT</pubDate><source url="https://m">Mint</source></item>
    </channel></rss>"""
    items = news.parse(rss)
    assert [i["title"] for i in items] == ["TCS shares fall", "TCS bags order from UK bank"]
    assert [i["sentiment"] for i in items] == ["negative", "positive"]
    assert items[0]["publisher"] == "Mint"

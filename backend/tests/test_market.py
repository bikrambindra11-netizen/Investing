from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from backend.app import market_data
from backend.app.db import DailyPrice, IndexClose, Instrument, SessionLocal, init_db
from backend.app.live import LiveStore
from backend.app.main import _cache, app


def test_pct_change():
    assert market_data.pct_change(110, 100) == 10.0
    assert market_data.pct_change(90, 100) == -10.0
    assert market_data.pct_change(None, 100) is None
    assert market_data.pct_change(10, 0) is None


def test_market_hours():
    ist = market_data.IST
    assert market_data.market_hours_open(datetime(2026, 11, 24, 10, 0, tzinfo=ist))
    assert not market_data.market_hours_open(datetime(2026, 11, 24, 16, 0, tzinfo=ist))
    assert not market_data.market_hours_open(datetime(2026, 11, 22, 10, 0, tzinfo=ist))  # Sunday


def test_live_store_returns_only_changes():
    s = LiveStore()
    s.update({"A": {"ltp": 1, "cp": 1, "ltt": None}, "B": {"ltp": 2, "cp": 2, "ltt": None}})
    seq, all_ = s.since(0)
    assert set(all_) == {"A", "B"}
    s.update({"B": {"ltp": 3, "cp": 2, "ltt": None}})
    _, changed = s.since(seq)
    assert set(changed) == {"B"}


def _seed():
    init_db()
    d = date(2026, 11, 23)
    with SessionLocal() as s:
        s.add_all([
            Instrument(instrument_key="NSE_EQ|INE002A01018", exchange="NSE", symbol="RELIANCE",
                       name="RELIANCE INDUSTRIES", isin="INE002A01018", series="EQ"),
            Instrument(instrument_key="BSE_EQ|INE002A01018", exchange="BSE", symbol="RELIANCE",
                       name="RELIANCE INDUSTRIES", isin="INE002A01018", series="A"),
            Instrument(instrument_key="BSE_EQ|INE376L01013", exchange="BSE", symbol="RAJKSYN",
                       name="RAJKAMAL SYNTHETICS", isin="INE376L01013", series="X"),
            Instrument(instrument_key="NSE_EQ|INE999Z01019", exchange="NSE", symbol="NOTRADE",
                       name="NO TRADE LTD", isin="INE999Z01019", series="EQ"),
            DailyPrice(instrument_key="NSE_EQ|INE002A01018", trade_date=d, close=1351.0,
                       prev_close=1377.5, volume=100, turnover=5e9, source="NSE bhavcopy"),
            DailyPrice(instrument_key="BSE_EQ|INE002A01018", trade_date=d, close=1352.5,
                       prev_close=1375.1, volume=10, turnover=1e8, source="BSE bhavcopy"),
            DailyPrice(instrument_key="BSE_EQ|INE376L01013", trade_date=d, close=17.13,
                       prev_close=18.0, volume=288, turnover=4849, source="BSE bhavcopy"),
            IndexClose(name="Nifty 50", trade_date=date(2026, 11, 20), close=25800.6,
                       change=286.3, change_pct=1.12, source="NSE index close file"),
        ])
        s.commit()
    _cache.clear()


def test_market_api_one_row_per_company():
    _seed()
    with TestClient(app) as c:
        body = c.get("/api/market/stocks").json()
        tiles = c.get("/api/market/indices").json()
        status = c.get("/api/market/status").json()

    rows = {r["symbol"]: r for r in body["rows"]}
    assert body["count"] == 3
    rel = rows["RELIANCE"]
    assert rel["exchanges"] == ["NSE", "BSE"] and rel["key"] == "NSE_EQ|INE002A01018"
    assert rel["close"] == 1351.0 and rel["price_source"] == "NSE bhavcopy"
    assert rel["change_pct"] == -1.92
    assert rows["RAJKSYN"]["exchanges"] == ["BSE"] and rows["RAJKSYN"]["price_source"] == "BSE bhavcopy"
    # No price available -> null (shown as "not available"), never guessed
    assert rows["NOTRADE"]["close"] is None and rows["NOTRADE"]["change_pct"] is None
    assert body["as_of"] == {"NSE": "2026-11-23", "BSE": "2026-11-23"}

    n50 = next(t for t in tiles if t["label"] == "Nifty 50")
    assert n50["close"] == 25800.6 and n50["as_of"] == "2026-11-20"
    sensex = next(t for t in tiles if t["label"] == "Sensex")
    assert sensex["close"] is None  # no free end-of-day source; live only

    assert status["live"]["state"] in {"off", "needs_keys"}
    assert status["upstox_keys_set"] is False


def test_login_without_keys_explains():
    with TestClient(app) as c:
        r = c.get("/auth/upstox/login", follow_redirects=False)
    assert r.status_code == 400 and ".env" in r.json()["detail"]

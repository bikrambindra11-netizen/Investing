from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.sources import bhavcopy, nse_indices, upstox_auth, upstox_feed, upstox_instruments

FIX = Path(__file__).parent / "fixtures"


def test_nse_bhavcopy_keeps_only_company_shares():
    rows = bhavcopy.parse((FIX / "nse_bhav_sample.csv").read_text(), "NSE")
    # gold bond (IN00...) dropped; LENSKART block-deal (BL) row dropped, regular EQ row kept
    assert [r.symbol for r in rows] == ["RELIANCE", "TCS", "LENSKART"]
    assert rows[2].close == 714.50
    rel = rows[0]
    assert rel.instrument_key == "NSE_EQ|INE002A01018"
    assert rel.trade_date == date(2026, 11, 23)
    assert rel.close == 1351.00 and rel.prev_close == 1377.50
    assert rel.volume and rel.volume > 0


def test_bse_bhavcopy():
    rows = bhavcopy.parse((FIX / "bse_bhav_sample.csv").read_text(), "BSE")
    assert {r.symbol for r in rows} == {"RELIANCE", "RAJKSYN"}
    assert rows[0].instrument_key == "BSE_EQ|INE002A01018"


def test_bhavcopy_rejects_html_page():
    with pytest.raises(ValueError):
        bhavcopy.parse("<!DOCTYPE html><html>...", "BSE")


def test_fetch_latest_skips_missing_days_and_weekends(monkeypatch):
    tried = []

    def fake(ex, d):
        tried.append(d)
        if d == date(2026, 11, 20):
            return ["ok"]
        raise bhavcopy.NotFound(d)

    monkeypatch.setattr(bhavcopy, "_fetch_day", fake)
    # Tuesday 24th -> Mon 23rd -> (skip Sun/Sat) -> Fri 20th
    assert bhavcopy.fetch_latest("NSE", date(2026, 11, 24)) == ["ok"]
    assert tried == [date(2026, 11, 24), date(2026, 11, 23), date(2026, 11, 20)]


def test_nse_index_file():
    rows = nse_indices.parse((FIX / "nse_index_sample.csv").read_text())
    n50 = rows[0]
    assert n50.name == "Nifty 50" and n50.trade_date == date(2026, 11, 20)
    assert n50.close == 25800.6 and n50.change_pct == 1.12


def test_instrument_filter():
    recs = [
        {"segment": "NSE_EQ", "instrument_type": "EQ", "isin": "INE002A01018", "exchange": "NSE",
         "instrument_key": "NSE_EQ|INE002A01018", "trading_symbol": "RELIANCE", "name": "RELIANCE"},
        {"segment": "NSE_EQ", "instrument_type": "SG", "isin": "IN2920250163", "exchange": "NSE",
         "instrument_key": "NSE_EQ|IN2920250163", "trading_symbol": "749RJ35", "name": "SDL"},
        {"segment": "BSE_EQ", "instrument_type": "F", "isin": "INE123X01011", "exchange": "BSE",
         "instrument_key": "BSE_EQ|INE123X01011", "trading_symbol": "DEBT", "name": "debt"},
        {"segment": "BSE_EQ", "instrument_type": "X", "isin": "INE376L01013", "exchange": "BSE",
         "instrument_key": "BSE_EQ|INE376L01013", "trading_symbol": "RAJKSYN", "name": "RAJKAMAL"},
        {"segment": "NSE_FO", "instrument_type": "FUT", "exchange": "NSE",
         "instrument_key": "NSE_FO|1", "trading_symbol": "X"},
    ]
    assert [r.symbol for r in upstox_instruments.parse(recs)] == ["RELIANCE", "RAJKSYN"]


def test_token_expiry_is_next_330am_ist():
    # 10:00 IST on 24 Nov -> 03:30 IST on 25 Nov
    issued = datetime(2026, 11, 24, 4, 30, tzinfo=timezone.utc)
    exp = upstox_auth.token_expiry(issued)
    assert exp.astimezone(upstox_auth.IST).isoformat() == "2026-11-25T03:30:00+05:30"
    # 02:00 IST -> 03:30 IST the same day
    early = datetime(2026, 11, 23, 20, 30, tzinfo=timezone.utc)
    assert upstox_auth.token_expiry(early).astimezone(upstox_auth.IST).day == 24


def test_login_url_has_client_and_state():
    url = upstox_auth.login_url("KEY", "http://127.0.0.1:8000/cb", "abc")
    assert "client_id=KEY" in url and "state=abc" in url and url.startswith(upstox_auth.DIALOG_URL)


def test_parse_feed_message():
    pb = upstox_feed.pb
    msg = pb.FeedResponse()
    f = msg.feeds["NSE_EQ|INE002A01018"]
    f.ltpc.ltp, f.ltpc.cp, f.ltpc.ltt = 1360.5, 1351.0, 1764000000000
    idx = msg.feeds["NSE_INDEX|Nifty 50"]
    idx.fullFeed.indexFF.ltpc.ltp = 25900.0
    ticks, _ = upstox_feed.parse_message(msg.SerializeToString())
    assert ticks["NSE_EQ|INE002A01018"]["ltp"] == 1360.5
    assert ticks["NSE_EQ|INE002A01018"]["cp"] == 1351.0
    assert ticks["NSE_EQ|INE002A01018"]["ltt"].year == 2025
    assert ticks["NSE_INDEX|Nifty 50"]["ltp"] == 25900.0

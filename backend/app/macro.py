"""Macro indicators: download, store, and judge each as tailwind / neutral / headwind."""
import logging
from functools import lru_cache
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml
from sqlalchemy import delete, select

from backend.sources import fred, mospi, rbi

from .db import MacroPoint, SessionLocal

log = logging.getLogger(__name__)
CONFIG = Path(__file__).resolve().parents[1] / "config"
SOURCES = {"fred": fred.SOURCE, "mospi_cpi": mospi.SOURCE, "mospi_iip": mospi.SOURCE,
           "mospi_gdp": mospi.SOURCE, "rbi": rbi.SOURCE}


@lru_cache
def load_series() -> dict[str, dict]:
    return yaml.safe_load((CONFIG / "macro_series.yaml").read_text())["series"]


@lru_cache
@lru_cache(maxsize=1)
def _overrides() -> dict[str, str]:
    return yaml.safe_load((CONFIG / "industry_drivers.yaml").read_text()).get("name_overrides") or {}


def load_industries() -> dict[str, dict]:
    return yaml.safe_load((CONFIG / "industry_drivers.yaml").read_text())["industries"]


# ------------------------------------------------------------------ download

def _store(series_id: str, points: list[tuple[str, float]], replace: bool = True) -> int:
    with SessionLocal() as s:
        if replace:
            s.execute(delete(MacroPoint).where(MacroPoint.series_id == series_id))
        for d, v in points:
            s.merge(MacroPoint(series_id=series_id, date=d, value=v))
        s.commit()
    return len(points)


def refresh_macro(today: date, only: set[str] | None = None) -> dict[str, str]:
    """Download every configured series (or just `only`). Returns {series_id: 'ok: n points' | 'error: ...'}."""
    cfg = {k: v for k, v in load_series().items() if only is None or k in only}
    result: dict[str, str] = {}
    years = [today.year - 2, today.year - 1, today.year]
    cache: dict[str, object] = {}

    def mospi_table(kind: str):
        """Each source table is downloaded once per refresh; a failure is remembered too."""
        if kind not in cache:
            try:
                cache[kind] = {"mospi_cpi": lambda: mospi.cpi(years, today), "mospi_iip": lambda: mospi.iip(years),
                               "mospi_gdp": mospi.gdp_growth, "rbi": rbi.fetch}[kind]()
            except Exception as e:
                cache[kind] = e
        if isinstance(cache[kind], Exception):
            raise cache[kind]
        return cache[kind]

    for sid, c in cfg.items():
        try:
            src = c["source"]
            if src == "fred":
                pts = fred.fetch(c["ref"], start=(today - timedelta(days=365 * 6)).isoformat())
            elif src in ("mospi_cpi", "mospi_iip"):
                table = mospi_table(src)
                if c["ref"] not in table:
                    raise ValueError(f"'{c['ref']}' not found in {src}")
                pts = table[c["ref"]]
            elif src == "mospi_gdp":
                pts = mospi_table(src)
            elif src == "rbi":
                rates = mospi_table(src)
                pts = [(today.isoformat(), rates[c["ref"]])]
                _store(sid, pts, replace=False)  # keep a daily history of snapshots
                result[sid] = "ok: snapshot"
                continue
            else:
                raise ValueError(f"unknown source {src}")
            if not pts:
                raise ValueError("no data returned")
            result[sid] = f"ok: {_store(sid, sorted(pts))} points"
        except Exception as e:  # one failing source must not stop the others
            result[sid] = f"error: {e}"
            log.warning("macro %s failed: %s", sid, e)
    return result


# ------------------------------------------------------------------ analysis

def _points(series_id: str) -> list[tuple[str, float]]:
    with SessionLocal() as s:
        rows = s.scalars(select(MacroPoint).where(MacroPoint.series_id == series_id)
                         .order_by(MacroPoint.date)).all()
        return [(r.date, r.value) for r in rows]


def _value_near(points: list[tuple[str, float]], target: date, tolerance_days: int = 45) -> tuple[str, float] | None:
    best = None
    for d, v in points:
        gap = abs((date.fromisoformat(d) - target).days)
        if gap <= tolerance_days and (best is None or gap < best[0]):
            best = (gap, (d, v))
    return best[1] if best else None


def yoy(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    out = []
    for d, v in points:
        prev = _value_near(points, date.fromisoformat(d) - timedelta(days=365), 20)
        if prev and prev[1]:
            out.append((d, round((v / prev[1] - 1) * 100, 2)))
    return out


def monthly(points: list[tuple[str, float]], months: int = 13) -> list[tuple[str, float]]:
    """Last value of each month, for the trend sparkline."""
    by_month: dict[str, tuple[str, float]] = {}
    for d, v in points:
        by_month[d[:7]] = (d, v)
    return [by_month[k] for k in sorted(by_month)][-months:]


def _fmt(v: float, unit: str) -> str:
    if unit in ("%", "% YoY"):
        return f"{v:.2f}%"
    return f"{v:,.2f} {unit}"


def judge(cfg: dict, points: list[tuple[str, float]], good: str = "up") -> dict:
    """Plain-language verdict for one indicator.

    level:   compares the latest value with the value ~12 months earlier.
    reading: compares the latest 3-period average with hi / lo thresholds.
    `good` says whether a rise (or a high reading) helps the industry.
    """
    if cfg.get("transform") == "yoy":
        points = yoy(points)
    if not points:
        return {"verdict": "not available", "summary": "No data available.", "latest": None}
    latest_d, latest_v = points[-1]
    unit = cfg["unit"]
    base = {"latest": latest_v, "latest_date": latest_d, "latest_text": _fmt(latest_v, unit),
            "trend": monthly(points)}

    if cfg["kind"] == "level":
        prev = _value_near(points, date.fromisoformat(latest_d) - timedelta(days=365))
        if not prev:
            return {**base, "verdict": "neutral", "direction": "unknown",
                    "summary": "Not enough history yet to see a 12-month trend.", "change_text": None}
        if "band_pct" in cfg:
            change = (latest_v / prev[1] - 1) * 100
            change_text, moved = f"{change:+.1f}% in 12 months", abs(change) >= cfg["band_pct"]
        else:
            change = latest_v - prev[1]
            change_text, moved = f"{change:+.2f} points in 12 months", abs(change) >= cfg["band_pts"]
        direction = "flat" if not moved else ("up" if change > 0 else "down")
        base.update(change_text=change_text, previous=prev[1], previous_date=prev[0])
    else:
        recent = [v for _, v in points[-3:]]
        avg = sum(recent) / len(recent)
        direction = "up" if avg >= cfg["hi"] else ("down" if avg < cfg["lo"] else "flat")
        base.update(change_text=f"3-period average {avg:.1f}% (high ≥ {cfg['hi']}%, low < {cfg['lo']}%)",
                    average=round(avg, 2))

    if direction == "flat":
        verdict = "neutral"
    else:
        verdict = "tailwind" if (direction == "up") == (good == "up") else "headwind"
    word = {"up": "rising" if cfg["kind"] == "level" else "high",
            "down": "falling" if cfg["kind"] == "level" else "low",
            "flat": "steady" if cfg["kind"] == "level" else "moderate"}[direction]
    return {**base, "verdict": verdict, "direction": direction, "summary": f"{cfg['label']} is {word}."}


def indicator(series_id: str, good: str = "up") -> dict:
    cfg = load_series()[series_id]
    return {"id": series_id, "label": cfg["label"], "unit": cfg["unit"],
            "source": SOURCES.get(cfg["source"], cfg["source"]),
            **judge(cfg, _points(series_id), good)}


def all_indicators() -> list[dict]:
    return [indicator(sid) for sid in load_series()]


# ------------------------------------------------------------------ industries

def resolve_industry(upstox_sector: str | None, name: str | None, nse_sector: str | None) -> str:
    inds = load_industries()
    nm = f" {(name or '').lower()} "
    # 1. Explicit name overrides (companies the generic sector names put in the wrong place)
    for pat, iid in _overrides().items():
        if pat in nm:
            return iid
    # 2. NSE sectors that are more precise than the data feed's (e.g. "Construction" covers both developers and contractors)
    if nse_sector == "Realty":
        return "realty"
    text = (upstox_sector or "").lower()
    if text:
        for iid, ind in inds.items():
            if any(w in text for w in ind.get("match", [])):
                return iid
    for iid, ind in inds.items():
        if any(w in nm for w in ind.get("name_match", [])):
            if nse_sector in (None, "Financial Services") or iid not in ("banks", "nbfc"):
                return iid
    if nse_sector:
        for iid, ind in inds.items():
            if nse_sector in ind.get("nse_sectors", []):
                return iid
    return "general"


def industry_macro(industry_id: str) -> dict:
    ind = load_industries()[industry_id]
    drivers = []
    for d in ind["drivers"]:
        x = indicator(d["series"], d["good"])
        x["why"] = d["why"]
        x["good_when"] = "rising" if d["good"] == "up" else "falling"
        drivers.append(x)
    judged = [d for d in drivers if d["verdict"] in ("tailwind", "neutral", "headwind")]
    tail = sum(d["verdict"] == "tailwind" for d in judged)
    head = sum(d["verdict"] == "headwind" for d in judged)
    return {
        "industry": industry_id,
        "label": ind["label"],
        "drivers": drivers,
        "not_tracked": ind.get("not_tracked", []),
        "score": {"tailwinds": tail, "headwinds": head, "judged": len(judged),
                  "share_tailwinds": round(tail / len(judged), 2) if judged else None},
        "as_of": datetime.now().isoformat(timespec="seconds"),
    }

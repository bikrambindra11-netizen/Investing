"""How a stock moves with commodities, the rupee and the market (correlation and beta)."""
from datetime import date, timedelta
from statistics import mean, pstdev

from backend.sources import fred

DAILY = {"Nifty 50": None, "Brent crude": "DCOILBRENTEU", "USD/INR": "DEXINUS", "US 10-year yield": "DGS10"}
MONTHLY = {"Copper": "PCOPPUSDM", "Aluminium": "PALUMUSDM", "Iron ore": "PIORECRUSDM", "Coal": "PCOALAUUSDM",
           "LNG (Asia)": "PNGASJPUSDM", "Cotton": "PCOTTINDUSDM"}


def _returns(series: dict[str, float], dates: list[str]) -> dict[str, float]:
    out, prev = {}, None
    for d in dates:
        v = series.get(d)
        if v is not None and prev is not None and prev != 0:
            out[d] = v / prev - 1
        if v is not None:
            prev = v
    return out


def corr(a: dict[str, float], b: dict[str, float]) -> tuple[float | None, float | None, int]:
    common = sorted(set(a) & set(b))
    if len(common) < 12:
        return None, None, len(common)
    x, y = [a[d] for d in common], [b[d] for d in common]
    mx, my, sx, sy = mean(x), mean(y), pstdev(x), pstdev(y)
    if not sx or not sy:
        return None, None, len(common)
    cov = mean((p - mx) * (q - my) for p, q in zip(x, y))
    return round(cov / (sx * sy), 2), round(cov / (sy * sy), 2), len(common)


def describe(c: float) -> str:
    a = abs(c)
    s = "strongly" if a >= 0.6 else "moderately" if a >= 0.35 else "weakly" if a >= 0.15 else "hardly"
    if s == "hardly":
        return "hardly linked"
    return f"{s} moves {'with' if c > 0 else 'against'} it"


def analyse(stock: list[dict], nifty: list[dict], today: date) -> list[dict]:
    """Daily correlations over the last year, monthly ones over the last 5 years."""
    out = []
    year_ago = (today - timedelta(days=365)).isoformat()
    s_daily = {c["date"]: c["close"] for c in stock if c["date"] >= year_ago}
    s_ret = _returns(s_daily, sorted(s_daily))
    for name, sid in DAILY.items():
        try:
            if sid is None:
                ser = {c["date"]: c["close"] for c in nifty if c["date"] >= year_ago}
            else:
                ser = {d: v for d, v in fred.fetch(sid, start=year_ago)}
        except Exception:
            continue
        r = _returns(ser, sorted(ser))
        c, beta, n = corr(s_ret, r)
        if c is not None:
            out.append({"factor": name, "period": "daily, last 12 months", "correlation": c, "beta": beta, "observations": n,
                        "reading": f"{describe(c)}" + (f"; a 1% move in {name} has come with a {beta:+.2f}% move in the stock" if abs(c) >= 0.15 else "")})
    # monthly: stock's month-end closes
    five = (today - timedelta(days=365 * 5)).isoformat()
    month_end: dict[str, float] = {}
    for c in stock:
        if c["date"] >= five:
            month_end[c["date"][:7]] = c["close"]
    s_m = _returns(month_end, sorted(month_end))
    for name, sid in MONTHLY.items():
        try:
            ser = {d[:7]: v for d, v in fred.fetch(sid, start=five)}
        except Exception:
            continue
        r = _returns(ser, sorted(ser))
        c, beta, n = corr(s_m, r)
        if c is not None:
            out.append({"factor": name, "period": "monthly, last 5 years", "correlation": c, "beta": beta, "observations": n,
                        "reading": describe(c)})
    out.sort(key=lambda x: -abs(x["correlation"]))
    return out

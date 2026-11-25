"""Render the marked-up candle chart as a PNG, so the analyst can inspect the structure visually."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

UP, DOWN, ACCENT, FIB = "#12733f", "#b42318", "#0d5c4a", "#8a5a00"
SHORT = {"Bullish engulfing": "Bull engulf", "Bearish engulfing": "Bear engulf", "Three white soldiers": "3 soldiers",
         "Three black crows": "3 crows", "Bullish marubozu": "Bull marubozu", "Bearish marubozu": "Bear marubozu",
         "Bullish harami": "Bull harami", "Bearish harami": "Bear harami"}
BEARISH = {"Bearish engulfing", "Shooting star", "Evening star", "Three black crows", "Bearish marubozu", "Bearish harami", "Gap down"}


def render(path: str, symbol: str, candles: list[dict], tech: dict, struct: dict, days: int = 180) -> str:
    n_all = len(candles)
    start = max(0, n_all - days)
    c = candles[start:]
    n = len(c)
    fig, (ax, axv) = plt.subplots(2, 1, figsize=(15, 8.5), sharex=True, gridspec_kw={"height_ratios": [4, 1]})
    for i, x in enumerate(c):
        col = UP if x["close"] >= x["open"] else DOWN
        ax.plot([i, i], [x["low"], x["high"]], color=col, linewidth=0.8)
        ax.add_patch(Rectangle((i - 0.3, min(x["open"], x["close"])), 0.6, max(abs(x["close"] - x["open"]), 1e-6), color=col))
        axv.bar(i, x["volume"], color=col, width=0.7)
    closes = [x["close"] for x in candles]
    for w, style, colr in ((20, ":", "#64748b"), (50, "-", "#2563eb"), (200, "--", "#7c3aed")):
        ma = [sum(closes[j - w + 1:j + 1]) / w if j >= w - 1 else None for j in range(start, n_all)]
        if any(v is not None for v in ma):
            ax.plot(range(n), ma, style, color=colr, linewidth=1.1, label=f"{w}-day average")
    for l in tech.get("supports", []):
        ax.axhline(l["level"], color=UP, linestyle="--", linewidth=1)
        ax.text(n + 0.5, l["level"], f"S ₹{l['level']:,.2f}", color=UP, va="center", fontsize=8)
    for l in tech.get("resistances", []):
        ax.axhline(l["level"], color=DOWN, linestyle="--", linewidth=1)
        ax.text(n + 0.5, l["level"], f"R ₹{l['level']:,.2f}", color=DOWN, va="center", fontsize=8)
    fib = struct.get("fibonacci")
    if fib:
        for lv in fib["levels"]:
            ax.axhline(lv["price"], color=FIB, linestyle=":", linewidth=0.8)
            ax.text(1, lv["price"], f"Fib {lv['ratio']} ₹{lv['price']:,.2f}", color=FIB, fontsize=7, va="bottom")
    for t in struct.get("trend_lines", []):
        i1 = n - 1 - t["from"]["bars_ago"]
        slope = t["slope_per_day"]
        x0 = max(i1, 0)
        ax.plot([x0, n - 1], [t["from"]["price"] + slope * (x0 - i1), t["from"]["price"] + slope * (n - 1 - i1)],
                color=ACCENT, linewidth=1.6, label=f"{t['kind']} trend line")
    for p in struct.get("chart_patterns", []):
        ax.axhline(p["neckline"], color="#0ea5e9", linestyle="-.", linewidth=0.9)
        ax.text(n * 0.5, p["neckline"], f"{p['pattern']} neckline ₹{p['neckline']:,.2f}", color="#0ea5e9", fontsize=7, va="bottom")
    dates = [x["date"] for x in c]
    recent = [p for p in struct.get("candles", []) if p["date"] in dates[-25:]]
    seen: dict[str, int] = {}
    for p in recent:
        i = dates.index(p["date"])
        k = seen.get(p["date"], 0)
        seen[p["date"]] = k + 1
        bear = p["pattern"] in BEARISH
        y = c[i]["high"] if bear else c[i]["low"]
        ax.scatter([i], [y], marker="v" if bear else "^", color=DOWN if bear else UP, s=28, zorder=5)
        ax.annotate(SHORT.get(p["pattern"], p["pattern"]), (i, y), xytext=(0, (12 + 10 * k) * (1 if bear else -1)),
                    textcoords="offset points", fontsize=6.5, ha="center", va="bottom" if bear else "top", color="#333")
    step = max(1, n // 9)
    axv.set_xticks(range(0, n, step))
    axv.set_xticklabels([dates[i] for i in range(0, n, step)], rotation=30, fontsize=8)
    ax.set_xlim(-1, n + 8)
    ax.set_title(f"{symbol}: last {n} sessions — support/resistance, Fibonacci, trend lines, patterns (last 25 sessions)")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path

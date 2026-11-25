"""India official statistics from MoSPI's eSankhyiki API (api.mospi.gov.in, no key needed)."""
import calendar
from datetime import date

import httpx

BASE = "https://api.mospi.gov.in"
SOURCE = "MoSPI eSankhyiki"
MONTHS = {m: i for i, m in enumerate(calendar.month_name) if m}


def _get_all(path: str, params: dict, max_pages: int = 30) -> list[dict]:
    rows, page = [], 1
    while page <= max_pages:
        last = None
        for _ in range(3):
            try:
                r = httpx.get(BASE + path, params={**params, "Format": "JSON", "limit": 100, "page": page},
                              headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
                r.raise_for_status()
                body = r.json()
                break
            except (httpx.HTTPError, ValueError) as e:
                last = e
        else:
            raise RuntimeError(f"MoSPI {path} failed: {last}")
        rows += body.get("data") or []
        meta = body.get("meta_data") or {}
        if page >= int(meta.get("totalPages") or 1):
            break
        page += 1
    return rows


def _month_end(year: int, month_name: str) -> str:
    m = MONTHS[month_name]
    return date(year, m, calendar.monthrange(year, m)[1]).isoformat()


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_cpi(rows: list[dict]) -> dict[str, list[tuple[str, float]]]:
    """All-India Combined CPI inflation (% YoY) by division, e.g. 'CPI (General)'."""
    out: dict[str, list] = {}
    for r in rows:
        if r.get("sector") != "Combined" or r.get("state") != "All India" or r.get("group"):
            continue
        v = _num(r.get("inflation"))
        if v is not None:
            out.setdefault(r["division"], []).append((_month_end(int(r["year"]), r["month"]), v))
    return out


CPI_BASE = {"base_year": "2024", "series": "Current", "sector_code": 3, "state_code": 1}  # Combined, All India


def cpi(years: list[int], today: date | None = None) -> dict[str, list[tuple[str, float]]]:
    """Headline and food CPI inflation. The API returns every item below a division, so the
    headline (division 0, no items) is fetched in one call and food month by month (first page)."""
    today = today or date.today()
    rows = _get_all("/api/cpi/getCPIData", {**CPI_BASE, "division_code": 0,
                                             "year": ",".join(map(str, years))})
    y, m = today.year, today.month
    for _ in range(14):  # food: last 14 months, one small request each
        try:
            rows += _get_all("/api/cpi/getCPIData", {**CPI_BASE, "division_code": 1, "year": y,
                                                      "month_code": m}, max_pages=1)
        except RuntimeError:
            pass
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return parse_cpi(rows)


def parse_iip(rows: list[dict]) -> dict[str, list[tuple[str, float]]]:
    """IIP growth (% YoY) keyed by 'category' or 'category|sub_category'."""
    out: dict[str, list] = {}
    for r in rows:
        v = _num(r.get("growth_rate"))
        if v is None:
            continue
        key = r["category"] + (f"|{r['sub_category']}" if r.get("sub_category") else "")
        out.setdefault(key, []).append((_month_end(int(r["year"]), r["month"]), v))
    return out


def iip(years: list[int]) -> dict[str, list[tuple[str, float]]]:
    rows = _get_all("/api/iip/getIipData", {"base_year": "2022-23", "frequency": "Monthly", "type": "All",
                                             "year": ",".join(map(str, years))})
    return parse_iip(rows)


QUARTER_END = {"Q1": (0, 6, 30), "Q2": (0, 9, 30), "Q3": (0, 12, 31), "Q4": (1, 3, 31)}


def parse_gdp(rows: list[dict]) -> list[tuple[str, float]]:
    """Real GDP growth (% YoY, constant prices) by quarter end date. FY '2026-27' Q1 = Apr-Jun 2026."""
    out = []
    for r in rows:
        v = _num(r.get("constant_price"))
        q = QUARTER_END.get(r.get("quarter"))
        if v is None or not q:
            continue
        fy_start = int(r["year"][:4])
        out.append((date(fy_start + q[0], q[1], q[2]).isoformat(), v))
    return out


def gdp_growth() -> list[tuple[str, float]]:
    rows = _get_all("/api/nas/getNASData", {"base_year": "2022-23", "series": "Current",
                                             "frequency_code": "Quarterly", "indicator_code": "22"})
    return parse_gdp(rows)

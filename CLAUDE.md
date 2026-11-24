# Stock Picker Portal: project brief for Claude Code

## What we are building

A personal web portal for Indian equities (NSE + BSE) that helps pick stocks using both
micro (company) and macro (economy and industry) analysis.

User flow:

1. **Home / Market page**: every NSE and BSE listed stock with live price, % change, volume.
   Searchable, sortable, with top gainers, top losers and index tiles (Nifty 50, Sensex,
   sector indices).
2. **Stock page**: user picks a stock. The portal automatically detects its industry using the
   NSE 4-level classification (Macro-Economic Sector > Sector > Industry > Basic Industry)
   and shows it.
3. **Industry page** (opens from the stock page, or by choosing an industry directly):
   - Macro panel: the macro indicators that drive THIS industry, with latest value, trend and a
     plain-language "tailwind / neutral / headwind" verdict for each.
   - Industry peers table: all listed companies in the same Basic Industry, with key ratios
     side by side.
4. **Micro panel** (on the stock page): company analysis following the framework below.
5. **News panel** (on both stock and industry pages): latest news and exchange announcements
   for the stock and its industry, each tagged positive / negative / neutral.
6. **Final summary card**: one plain-English verdict combining macro + micro + valuation, with
   the reasons listed. Outputs must be simple enough for a non-expert to read.

## Tech stack

- Frontend: Next.js (React, TypeScript), Tailwind CSS, a charting library (Recharts or
  lightweight-charts).
- Backend: Python FastAPI (Python because the data libraries, pandas and MoSPI client are Python).
- Database: SQLite to start, PostgreSQL later. Cache all slow-changing data (fundamentals, macro).
- Live prices: backend holds one WebSocket connection to the broker feed and pushes ticks to the
  browser over a WebSocket/SSE endpoint.
- Scheduled jobs (APScheduler): refresh instrument list daily, fundamentals weekly, macro data
  daily (most series are monthly), news every few minutes during market hours.
- All API keys in `.env` (never commit it; add to `.gitignore`).

## Data sources

| Need | Source | Notes |
|---|---|---|
| Live prices, OHLC, historical candles | Upstox Developer API (REST + WebSocket) | Free for Upstox account holders. Use the official Python SDK. Handle token expiry. |
| Fundamentals | Upstox API fundamentals endpoints; fallback: company results filed on NSE/BSE | Store 5-10 years per company. |
| Industry classification | NSE equity list / quote data (4-level industry) | Build a `stock -> basic_industry` table. Map BSE-only stocks via BSE's industry field. |
| India macro (CPI, WPI, IIP, GDP, unemployment) | MoSPI eSankhyiki API (`mospi-esankhyiki` Python package) | Follow its discovery order: list_datasets -> get_indicators -> get_metadata -> get_data. |
| Rates, credit growth, forex reserves, USD/INR | RBI DBIE | Repo rate, bank credit by sector, forex. |
| Global macro (US yields, Fed rate, DXY) | FRED API | Free key. |
| Commodities (crude, metals, coal, gold) | FRED / free commodity feeds | Needed for sector drivers. |
| News | NSE/BSE corporate announcements + Google News RSS per stock and per industry | Sentiment tag with a simple model or rules. |

Data use rule: this is for personal use. Exchange data vending rules restrict showing broker
feed data publicly; do not make the site public without a licensed data feed.

## Industry -> macro driver map

Keep this in an editable config file `backend/config/industry_drivers.yaml` so drivers can be
added without code changes. Starting map (extend for every Basic Industry):

- Banks / NBFCs: repo rate, bank credit growth, CPI, 10Y G-sec yield
- IT services: USD/INR, US GDP growth, US 10Y yield
- Cement: IIP cement index, govt infra capex, coal/petcoke prices, housing demand
- Metals (steel, aluminium): global metal prices, China demand indicators, IIP metals, coal prices
- Power: electricity demand (IIP electricity), coal prices, renewable capacity additions
- Oil & gas / refining: crude oil price, USD/INR, refining margins
- Auto: IIP auto, fuel prices, rural demand indicators, interest rates
- FMCG: CPI food inflation, rural wages, monsoon
- Pharma: USD/INR, US generic pricing news
- Capital goods / defence: govt capex, order inflows, IIP capital goods
- Gold / precious metal ETFs: US real yields, DXY, Fed rate, CPI

Each driver shows: latest value, 12-month trend, and verdict (tailwind / neutral / headwind) with
a one-line reason in plain English.

## Micro framework (company analysis)

Follow this order on the stock page:

1. Business: what the company does, segments and revenue split, value chain position.
2. Industry position: market share, capacity utilisation, competitors (peer table).
3. Financials (5 years history): revenue, EBITDA, PAT growth; margins; ROE, ROCE; debt/equity;
   interest cover; cash flow from operations vs profit; working capital days.
4. Capital allocation: capex, dividends, buybacks, acquisitions.
5. Shareholding: promoter %, pledge %, FII, DII, retail trend over 8 quarters.
6. Valuation: show only the 2 most relevant of P/E, P/B, EV/EBITDA, EV/replacement cost, DCF
   (choose by industry: e.g. P/B for banks, EV/EBITDA for capital-heavy businesses), versus the
   company's own 5-year average and versus peers.
7. Graham defensive investor checks (pass / fail each, with the number shown):
   adequate size; current ratio >= 2 and long-term debt <= net current assets; positive earnings
   every year for 10 years; uninterrupted dividends; EPS growth >= 33% over 10 years (3-year
   averages); P/E <= 15 on 3-year average EPS; P/B <= 1.5 or P/E x P/B <= 22.5.
   Banks/financials: skip the current-ratio test and say why.
8. Risks: list the key risks in plain English.

## Scoring (keep it simple)

- Macro score: share of the industry's drivers that are tailwinds.
- Micro score: quality (growth, margins, ROCE, debt) + Graham checks passed.
- Valuation: cheap / fair / expensive versus own history and peers.
- Final card: verdict in one sentence plus 3-5 reasons. Always show the underlying numbers.
- Never present the verdict as investment advice; label it as a screening output.

## Build phases (finish and test each before the next)

1. Project setup: Next.js + FastAPI + SQLite skeleton, `.env`, README with run commands.
2. Market page: load full NSE + BSE instrument list, live prices via Upstox WebSocket, search,
   sort, gainers/losers, index tiles. Test: prices update live during market hours, last close
   shown after hours.
3. Stock page + industry detection: price chart, key stats, 4-level industry shown automatically.
4. Macro layer: MoSPI, RBI, FRED fetchers with caching; industry driver config; industry page
   macro panel.
5. Micro layer: fundamentals store, ratios, peer table, Graham checks, valuation.
6. News panel with sentiment tags for stock and industry.
7. Scoring and final summary card.
8. Polish: mobile layout, loading states, error messages when a data source is down.

## Coding rules

- Every data fetcher in its own module under `backend/sources/` with retries and caching.
- Never hardcode keys. Never guess figures: if data is missing, show "not available".
- Show the data source and "as of" date beside every number.
- Write simple tests for each fetcher and ratio calculation.

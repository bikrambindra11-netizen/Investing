# Stock Picker Portal

A personal website for picking Indian stocks (NSE + BSE). For any stock it shows:

- **Price**: live (with Upstox) or last close, a 10-year chart, 52-week range and returns.
- **Industry**: detected automatically (macro-economic sector → sector → industry → basic industry).
- **Economy check**: the economic factors that matter for that industry (interest rates, inflation,
  crude, metal prices, factory output…), each marked **tailwind / neutral / headwind** with a reason.
- **Company analysis**: business, competitors, 5+ years of financials, cash flow, capital allocation,
  shareholding, valuation versus its own history and its sector, Graham's defensive-investor checks,
  and key risks.
- **News** with positive / negative / neutral tags.
- **A one-line summary** with the reasons behind it.

> Personal screening tool only. **Not investment advice.** Do not put this site on the public
> internet: exchange rules do not allow re-publishing broker market data.

---

## How to start it (no coding needed)

**One-time installs** (free):
1. **Python** — https://www.python.org/downloads/ (on Windows, tick **"Add Python to PATH"** during install).
2. **Node.js** (LTS version) — https://nodejs.org/
3. **This project** — on GitHub click the green **Code** button → **Download ZIP**, then unzip it.

**Start the portal:**
- **Windows:** double-click **`start-windows.bat`**.
- **Mac:** double-click **`start-mac.command`**. (First time only: if macOS blocks it, right-click → **Open** → **Open**.)

The first start takes a few minutes (it installs packages and downloads data). Your browser then opens
**http://localhost:3000**. Keep the black window(s) open while you use it; close them to stop.

## Turning on live prices and company financials (free Upstox account)

Without this you still get prices (last close), charts, industries, the economy check and news.
With it you also get **live prices** and **company financials** (the full analysis).

1. Open an Upstox account if you don't have one.
2. Go to **account.upstox.com/developer/apps** → **New App**. Set the redirect URL to
   `http://127.0.0.1:8000/auth/upstox/callback`. Copy the **API Key** and **API Secret**.
3. In the project folder, open the file **`.env`** with Notepad (Windows) or TextEdit (Mac) and fill in:
   ```
   UPSTOX_API_KEY=your-api-key
   UPSTOX_API_SECRET=your-api-secret
   ```
   Save, then close and restart the portal.
4. On the market page click **Login with Upstox**. Upstox logs you out at 3:30 AM every day,
   so click it once per day.

Never share your `.env` file or paste the keys anywhere else.

---

## Pages

| Page | What it shows |
|---|---|
| **Market** | Every NSE + BSE stock: price, change, volume; search, sort, top gainers/losers, index tiles |
| **Stock** (click any stock) | Summary, chart, industry, economy check, the 8-step company analysis, peers, news |
| **Industries** | All industries ranked by how supportive the economy currently is |
| **Industry** | Economy check, companies in the industry with their ratios, industry news |
| **Economy** | All 41 tracked economic indicators with trends |

## Where the data comes from

| Data | Source | Needs Upstox login? |
|---|---|---|
| Stock list | Upstox public instrument file | No |
| Daily closing prices, index values | NSE and BSE daily files | No |
| 10-year price history | Upstox historical candles | No |
| Sector | NSE index lists (about 750 larger companies) | No |
| India inflation, factory output, GDP | MoSPI (Government of India) | No |
| Repo rate | RBI website | No |
| US rates, dollar, crude, metals, coal | FRED (St. Louis Fed) | No |
| News | Google News | No |
| Live prices, Sensex | Upstox live feed | **Yes** |
| Financials, ratios, shareholding, competitors, detailed sector | Upstox fundamentals | **Yes** |

Every number on screen shows its source and date. When data is missing the portal says
"not available" — it never guesses.

### Known limits
- Free sources do not report debt, EBITDA, interest cover, working-capital days, promoter pledges,
  market share or capacity utilisation, so these are marked "not available".
- Graham's 10- and 20-year tests are marked **partial** when the source has fewer years.
- Live prices cover up to 5,000 stocks (Upstox limit); the rest show the last close.
- "Tailwind / headwind" rules and thresholds are simple and editable (see below).

## Customising

- `backend/config/industry_drivers.yaml` — which economic factors matter for which industry,
  and whether a rise helps or hurts.
- `backend/config/macro_series.yaml` — the indicators tracked and their thresholds.

Restart the portal after editing.

---

## For developers

```
backend/    FastAPI + SQLite (Python)
  app/        API, jobs, market data, macro engine, company analysis
  sources/    one module per data source, with retries and caching
  config/     editable YAML (industry drivers, macro indicators)
  tests/      pytest (offline; fixtures from real files and Upstox's documented samples)
frontend/   Next.js + TypeScript + Tailwind
```

Manual run:
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload            # http://127.0.0.1:8000 (API docs at /docs)
cd frontend && npm install && npm run dev        # http://localhost:3000
```
Tests: `pytest backend` and `cd frontend && npm run lint && npm run build`.

Background jobs: stock list and prices on weekdays at 08:30, 18:05 and 21:05 IST; economic data daily at 07:40 IST.

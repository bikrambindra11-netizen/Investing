# Stock Picker Portal

Personal NSE/BSE stock screening portal combining macro (economy and industry) and micro
(company) analysis. Full project brief: [CLAUDE.md](CLAUDE.md).

> Personal use only. Screening output, not investment advice. Do not make this site public
> without a licensed market data feed (exchange data vending rules).

## Layout

```
backend/    FastAPI + SQLite (Python)
  app/        API entry point, settings, database models
  sources/    one module per data source (Upstox, NSE, BSE, MoSPI, RBI, FRED, news)
  config/     industry_drivers.yaml (industry -> macro driver map)
  tests/
frontend/   Next.js + TypeScript + Tailwind
```

## First-time setup

Needs Python 3.11+ and Node 20+.

```bash
cp .env.example .env          # then fill in your keys (see below)

python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

cd frontend && npm install && cd ..
```

Keys (all free). The portal runs without any keys; it then shows the last closing prices.
- **Upstox** (live prices): needs an Upstox account. In the Upstox developer console
  (account.upstox.com/developer/apps) create an app with redirect URL
  `http://127.0.0.1:8000/auth/upstox/callback`, then put the API key and secret in `.env`.
- **FRED** (US/global macro): request a key at fred.stlouisfed.org. Needed from Phase 4.

## Run

Two terminals, both from the repo root:

```bash
# 1. Backend  -> http://127.0.0.1:8000  (API docs at /docs)
source .venv/bin/activate
uvicorn backend.app.main:app --reload

# 2. Frontend -> http://localhost:3000
cd frontend && npm run dev
```

Open http://localhost:3000.

- **First start** downloads the stock list and closing prices (about a minute). After that the
  backend refreshes them on weekdays at 08:30, 18:05 and 21:05 IST.
- **Live prices**: once the Upstox key and secret are in `.env`, click **Login with Upstox** on the
  market page. Upstox tokens expire at 3:30 AM IST, so log in once each trading day.
- The **Setup** page shows the backend status and which keys are set.

## Market page data

| What | Source | When |
|---|---|---|
| Stock list (NSE + BSE equities) | Upstox public instrument file | daily, no key needed |
| Last close, change, volume, traded value | NSE and BSE bhavcopy files | each evening, no key needed |
| Index tiles (Nifty and sector indices) | NSE daily index close file | each evening, no key needed |
| Live prices and Sensex | Upstox market data feed (WebSocket) | real time, needs Upstox login |

Notes:
- A company listed on both exchanges shows once, using its NSE price.
- Sensex has no free end-of-day file, so its tile shows "not available" until live prices are on.
- Upstox allows up to 5,000 instruments on one feed connection. The index tiles and the most
  traded stocks get live prices; the rest (thinly traded BSE-only stocks) show the last close.
- Volume and traded value are from the last full session, also while prices are live.
- "Market open" is judged from the live feed; without it, by the clock (09:15-15:30 IST,
  exchange holidays not checked).
- The live feed connection is opened with TLS certificate verification on. (The official Upstox
  SDK turns verification off, so only its message decoder is used.)

## Test

```bash
source .venv/bin/activate && pytest backend
cd frontend && npm run lint && npm run build
```

## Build progress

- [x] Phase 1: project skeleton
- [x] Phase 2: market page with live prices
- [ ] Phase 3: stock page + industry detection
- [ ] Phase 4: macro layer
- [ ] Phase 5: micro layer
- [ ] Phase 6: news panel
- [ ] Phase 7: scoring and summary card
- [ ] Phase 8: polish

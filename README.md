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

Keys (all free):
- **Upstox**: create an app at the Upstox developer console to get the API key and secret.
  The access token expires daily. Needed from Phase 2.
- **FRED**: request a key at fred.stlouisfed.org. Needed from Phase 4.

## Run

Two terminals, both from the repo root:

```bash
# 1. Backend  -> http://127.0.0.1:8000  (API docs at /docs)
source .venv/bin/activate
uvicorn backend.app.main:app --reload

# 2. Frontend -> http://localhost:3000
cd frontend && npm run dev
```

Open http://localhost:3000. The setup check page shows the backend status, database and
which keys are set.

## Test

```bash
source .venv/bin/activate && pytest backend
cd frontend && npm run lint && npm run build
```

## Build progress

- [x] Phase 1: project skeleton
- [ ] Phase 2: market page with live prices
- [ ] Phase 3: stock page + industry detection
- [ ] Phase 4: macro layer
- [ ] Phase 5: micro layer
- [ ] Phase 6: news panel
- [ ] Phase 7: scoring and summary card
- [ ] Phase 8: polish

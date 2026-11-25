#!/bin/bash
# Stock Picker Portal - double-click to start (macOS). Also works on Linux: ./start-mac.command
cd "$(dirname "$0")" || exit 1
echo
echo " ===== Stock Picker Portal ====="
echo

fail() { echo " $1"; read -r -p " Press Enter to close." _; exit 1; }

PY=$(command -v python3 || command -v python) || fail "Python is not installed. Install it from https://www.python.org/downloads/ and run this again."
command -v npm >/dev/null || fail "Node.js is not installed. Install the LTS version from https://nodejs.org/ and run this again."

if [ ! -f .env ]; then
  cp .env.example .env
  echo " Created .env (open it later to add your Upstox keys)"
fi
if [ ! -x .venv/bin/python ]; then
  echo " Setting up Python packages, first time only (1-3 minutes)..."
  "$PY" -m venv .venv || fail "Could not create the Python environment."
fi
.venv/bin/python -m pip install -q -r backend/requirements.txt || fail "Python package install failed. Check your internet."

cd frontend || exit 1
[ -d node_modules ] || echo " Setting up website packages, first time only (1-3 minutes)..."
npm install --no-audit --no-fund --loglevel=error || fail "Website package install failed. Check your internet."
echo " Preparing the website..."
npm run build --silent >/dev/null || fail "Website build failed."
cd ..

.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
BACK=$!
(cd frontend && npx next start -H 127.0.0.1 -p 3000) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null; exit 0' INT TERM EXIT

sleep 8
(open http://localhost:3000 2>/dev/null || xdg-open http://localhost:3000 2>/dev/null) &
echo
echo " The portal is running at http://localhost:3000"
echo " Keep this window open while you use it. Close it (or press Ctrl+C) to stop."
wait

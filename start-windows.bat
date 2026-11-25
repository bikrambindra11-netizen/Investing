@echo off
setlocal
title Stock Picker Portal
cd /d "%~dp0"

echo.
echo  ===== Stock Picker Portal =====
echo.

rem ---- Check Python and Node.js are installed
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" ( where py >nul 2>nul && set PY=py -3 )
if "%PY%"=="" (
  echo  Python is not installed.
  echo  Install it from https://www.python.org/downloads/  ^(tick "Add Python to PATH"^), then run this again.
  pause & exit /b 1
)
where npm >nul 2>nul || (
  echo  Node.js is not installed.
  echo  Install the LTS version from https://nodejs.org/ , then run this again.
  pause & exit /b 1
)

rem ---- First-time setup (skipped next time)
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo  Created .env  ^(open it in Notepad later to add your Upstox keys^)
)
if not exist ".venv\Scripts\python.exe" (
  echo  Setting up Python packages, first time only ^(1-3 minutes^)...
  %PY% -m venv .venv || ( echo  Could not create the Python environment. & pause & exit /b 1 )
)
".venv\Scripts\python.exe" -m pip install -q -r backend\requirements.txt || ( echo  Python package install failed. Check your internet. & pause & exit /b 1 )

pushd frontend
if not exist "node_modules" (
  echo  Setting up website packages, first time only ^(1-3 minutes^)...
)
call npm install --no-audit --no-fund --loglevel=error || ( echo  Website package install failed. Check your internet. & popd & pause & exit /b 1 )
echo  Preparing the website...
call npm run build --silent || ( echo  Website build failed. & popd & pause & exit /b 1 )
popd

rem ---- Start both parts in their own windows
start "Portal data server (keep open)" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"
start "Portal website (keep open)" cmd /k "cd frontend && npx next start -H 127.0.0.1 -p 3000"

echo  Starting... your browser will open in a few seconds.
timeout /t 8 >nul
start "" http://localhost:3000
echo.
echo  The portal is running. Keep the two new windows open while you use it.
echo  To stop it, close those two windows.
echo.
pause

@echo off
title RailCast AI Launcher
cd /d "%~dp0"

echo ============================================================
echo   RailCast AI - starting backend + frontend
echo ============================================================

if not exist "backend\.venv\Scripts\python.exe" (
    echo [!] Backend virtualenv missing. Run once:
    echo     cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
if not exist "frontend\node_modules" (
    echo [!] Frontend dependencies missing. Run once:
    echo     cd frontend ^&^& npm install
    pause
    exit /b 1
)

echo [1/2] Starting backend  (FastAPI  - http://127.0.0.1:8000)
start "RailCast Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [2/2] Starting frontend (Next.js  - http://localhost:3000)
start "RailCast Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo Waiting for servers to boot...
timeout /t 15 /nobreak >nul
start http://localhost:3000

echo.
echo RailCast AI is running:
echo   Dashboard : http://localhost:3000
echo   API docs  : http://127.0.0.1:8000/docs
echo.
echo To STOP: close the two "RailCast Backend/Frontend" windows
echo (or run stop-railcast.bat).
echo.
pause

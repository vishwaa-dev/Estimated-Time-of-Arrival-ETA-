@echo off
title RailCast AI Stop
echo Stopping anything listening on ports 8000 / 3000 ...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000,3000 -State Listen -ErrorAction SilentlyContinue | Select-Object -Unique OwningProcess | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo Done. RailCast AI servers stopped.
pause

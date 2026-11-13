@echo off
rem Double-click launcher for the agent observability proxy.
rem Runs the proxy with the defaults and keeps the window open
rem so you can read the logs and any exit error.
cd /d "%~dp0"
title Agent Observability Proxy
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
echo Starting proxy with %PY% ...
"%PY%" proxy.py --port 8888 --db "%~dp0attempts.db" --allowlist "127.0.0.1,localhost,::1" --rate-limit 100 --rate-window 10 --relay-timeout 30
echo.
echo Proxy exited with code %ERRORLEVEL%.
pause

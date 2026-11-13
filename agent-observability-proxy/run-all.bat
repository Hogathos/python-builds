@echo off
rem Double-click launcher: starts the proxy and the API together,
rem each in its own window. Closing one window stops only that one.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
echo Starting proxy and API in separate windows ...
start "Agent Observability Proxy" cmd /k "echo Proxy log: & %PY% proxy.py --port 8888 --db "%~dp0attempts.db" --allowlist 127.0.0.1,localhost,::1 --rate-limit 100 --rate-window 10 --relay-timeout 30 & echo. & echo Proxy exited. & pause"
start "Agent Observability API" cmd /k "echo API log: & %PY% -m uvicorn api:app --host 127.0.0.1 --port 8000 & echo. & echo API exited. & pause"

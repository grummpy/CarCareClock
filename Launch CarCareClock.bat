@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo CarCareClock needs Python 3.11 or newer, and python was not found.
  echo Install Python from https://www.python.org/downloads/ and then double-click this launcher again.
  pause
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo CarCareClock needs Python 3.11 or newer. This computer has:
  python --version
  echo Install a newer Python from https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist .venv (
  echo First run: creating a private environment and installing pinned packages...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)

.venv\Scripts\python.exe -m carcareclock
if errorlevel 1 pause
endlocal

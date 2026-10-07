#!/bin/bash
# Double-click this file on a Mac. The first run creates .venv and installs
# pinned packages. Later runs start the local app and open the browser.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "CarCareClock needs Python 3.11 or newer, and python3 was not found."
  echo "Install Python from https://www.python.org/downloads/ and then double-click this launcher again."
  exit 1
fi

py_ok="$(python3 -c 'import sys; print("1" if sys.version_info >= (3, 11) else "0")')"
if [ "$py_ok" != "1" ]; then
  echo "CarCareClock needs Python 3.11 or newer. This computer has:"
  python3 --version
  echo "Install a newer Python from https://www.python.org/downloads/"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "First run: creating a private environment and installing pinned packages..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python -m carcareclock

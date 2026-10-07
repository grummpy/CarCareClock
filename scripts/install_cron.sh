#!/bin/bash
# Writes a commented cron file. Does not install it. Registration is a separate opt-in.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m carcareclock install-checker cron "$@"

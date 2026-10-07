#!/bin/bash
# Writes a launchd plist. Does not load it. Registration is a separate opt-in.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m carcareclock install-checker launchd "$@"

#!/bin/zsh
set -euo pipefail

ROOT="."
LOG_DIR="$ROOT/logs/pilot"
mkdir -p "$LOG_DIR"

exec /usr/bin/python3 -u "$ROOT/scripts/nexus_sentinel_proxy.py" >> "$LOG_DIR/proxy.out.log" 2>> "$LOG_DIR/proxy.err.log"

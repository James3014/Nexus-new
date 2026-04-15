#!/bin/zsh
REPO_ROOT="."
PID_FILE="$REPO_ROOT/.nexus/learn_refresh_daemon.pid"
LOG_FILE="$REPO_ROOT/.nexus/learn_refresh_daemon.log"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[!] Learn refresh daemon already running (PID: $OLD_PID)"
    exit 0
  fi
fi

mkdir -p "$REPO_ROOT/.nexus"
cd "$REPO_ROOT"
nohup uv run python scripts/ops/learn_refresh_daemon.py "$@" > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "🚀 [Nexus] Learn refresh daemon started in background (PID: $!)"

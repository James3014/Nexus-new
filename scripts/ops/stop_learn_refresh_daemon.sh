#!/bin/zsh
REPO_ROOT="."
PID_FILE="$REPO_ROOT/.nexus/learn_refresh_daemon.pid"

if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  echo "⏹️ [Nexus] Stopping Learn refresh daemon (PID: $PID)..."
  kill "$PID" 2>/dev/null || pkill -f learn_refresh_daemon.py
  rm -f "$PID_FILE"
  echo "✅ STOPPED"
else
  pkill -f learn_refresh_daemon.py
  echo "[!] PID file not found, performed pkill."
fi

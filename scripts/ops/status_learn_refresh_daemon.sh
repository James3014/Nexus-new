#!/bin/zsh
REPO_ROOT="."
STATUS_FILE="$REPO_ROOT/.nexus/learn_refresh_daemon_status.json"
PID_FILE="$REPO_ROOT/.nexus/learn_refresh_daemon.pid"

if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "RUNNING PID=$PID"
  else
    echo "STALE_PID PID=$PID"
  fi
else
  echo "STOPPED"
fi

if [[ -f "$STATUS_FILE" ]]; then
  echo "--- status ---"
  cat "$STATUS_FILE"
fi

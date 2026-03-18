#!/bin/zsh
set -euo pipefail

NEXUS_ROOT="${NEXUS_ROOT:-/Users/jameschen/Workspace/nexus}"
STATE_DIR="$NEXUS_ROOT/.nexus"
PID_FILE="$STATE_DIR/runner_supervisor.pid"
CHILD_PID_FILE="$STATE_DIR/runner_supervisor_child.pid"

if [[ -f "$CHILD_PID_FILE" ]]; then
  CPID="$(cat "$CHILD_PID_FILE" 2>/dev/null || true)"
  if [[ -n "$CPID" ]] && kill -0 "$CPID" 2>/dev/null; then
    kill -TERM "$CPID" 2>/dev/null || true
    sleep 2
    kill -KILL "$CPID" 2>/dev/null || true
    echo "[stop] killed child pid=$CPID"
  fi
fi

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID" 2>/dev/null || true
    sleep 2
    kill -KILL "$PID" 2>/dev/null || true
    echo "[stop] killed supervisor pid=$PID"
  fi
fi

rm -f "$PID_FILE" "$CHILD_PID_FILE"
echo "[stop] done"

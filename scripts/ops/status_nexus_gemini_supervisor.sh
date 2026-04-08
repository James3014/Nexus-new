#!/bin/zsh
set -euo pipefail

NEXUS_ROOT="${NEXUS_ROOT:-.}"
STATE_DIR="$NEXUS_ROOT/.nexus"
PID_FILE="$STATE_DIR/runner_supervisor.pid"
CHILD_PID_FILE="$STATE_DIR/runner_supervisor_child.pid"
STATE_FILE="$STATE_DIR/runner_supervisor_state.json"
LOG_FILE="$STATE_DIR/runner_supervisor.log"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "[status] supervisor: running pid=$PID"
  else
    echo "[status] supervisor: stale pid file"
  fi
else
  echo "[status] supervisor: not running"
fi

if [[ -f "$CHILD_PID_FILE" ]]; then
  CPID="$(cat "$CHILD_PID_FILE" 2>/dev/null || true)"
  if [[ -n "$CPID" ]] && kill -0 "$CPID" 2>/dev/null; then
    echo "[status] child: running pid=$CPID"
  else
    echo "[status] child: not running"
  fi
fi

echo "[status] state: $STATE_FILE"
[[ -f "$STATE_FILE" ]] && sed -n '1,80p' "$STATE_FILE" || echo "(missing)"

echo "[status] log: $LOG_FILE"
[[ -f "$LOG_FILE" ]] && tail -n 40 "$LOG_FILE" || echo "(missing)"

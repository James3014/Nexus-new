#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SUPERVISOR="$SCRIPT_DIR/nexus_longrun_supervisor.sh"
NEXUS_ROOT="${NEXUS_ROOT:-/Users/jameschen/Workspace/nexus}"
STATE_DIR="$NEXUS_ROOT/.nexus"
PID_FILE="$STATE_DIR/runner_supervisor.pid"
STATE_FILE="$STATE_DIR/runner_supervisor_state.json"
LOG_FILE="$STATE_DIR/runner_supervisor.log"

mkdir -p "$STATE_DIR"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "[start] supervisor already running pid=$PID"
    echo "[start] state: $STATE_FILE"
    echo "[start] log: $LOG_FILE"
    exit 0
  fi
fi

nohup "$SUPERVISOR" >/dev/null 2>&1 &

for i in {1..12}; do
  if [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
      echo "[start] supervisor started pid=$PID"
      echo "[start] state: $STATE_FILE"
      echo "[start] log: $LOG_FILE"
      exit 0
    fi
  fi
  sleep 1
done

echo "[start] failed: supervisor did not become healthy within 12s" >&2
echo "[start] state: $STATE_FILE" >&2
[[ -f "$STATE_FILE" ]] && tail -n 80 "$STATE_FILE" >&2 || echo "(missing state)" >&2
echo "[start] log: $LOG_FILE" >&2
[[ -f "$LOG_FILE" ]] && tail -n 120 "$LOG_FILE" >&2 || echo "(missing log)" >&2
exit 1

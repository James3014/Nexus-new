#!/bin/zsh
set -euo pipefail

NEXUS_ROOT="${NEXUS_ROOT:-.}"
LONGRUN_SCRIPT="${LONGRUN_SCRIPT:-./scripts/ops/start_nexus_gemini_longrun.sh}"
MODEL="${MODEL:-gemini-3.1-pro-preview}"
APPROVAL_MODE="${APPROVAL_MODE:-yolo}"

SUPERVISOR_CHECK_SEC="${SUPERVISOR_CHECK_SEC:-15}"
SUPERVISOR_STALE_SEC="${SUPERVISOR_STALE_SEC:-1800}"

STATE_DIR="$NEXUS_ROOT/.nexus"
STATE_FILE="$STATE_DIR/runner_supervisor_state.json"
LOG_FILE="$STATE_DIR/runner_supervisor.log"
PID_FILE="$STATE_DIR/runner_supervisor.pid"
CHILD_PID_FILE="$STATE_DIR/runner_supervisor_child.pid"
TASK_STATUS_FILE="$STATE_DIR/task_status.json"
HEARTBEAT_FILE="$NEXUS_ROOT/docs/EXEC_LIVE_STATUS.md"
LONGRUN_LOG_DIR="$STATE_DIR/longrun_logs"

mkdir -p "$STATE_DIR" "$LONGRUN_LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[supervisor] already running pid=$OLD_PID"
    exit 0
  fi
fi

echo $$ > "$PID_FILE"
EXIT_REASON="unexpected_exit"

log() {
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[$ts] $1" | tee -a "$LOG_FILE"
}

write_state() {
  local curr_status="$1"
  local reason="$2"
  local child_pid="$3"
  local latest_round_log="$4"
  local task_mtime="$5"
  local heartbeat_mtime="$6"
  local round_mtime="$7"
  echo "{
  \"updated_at\": \"$(date '+%Y-%m-%d %H:%M:%S')\",
  \"status\": \"$curr_status\",
  \"reason\": \"$reason\",
  \"exit_reason\": \"$EXIT_REASON\",
  \"supervisor_pid\": \"$$\",
  \"child_pid\": \"$child_pid\",
  \"model\": \"$MODEL\",
  \"approval_mode\": \"$APPROVAL_MODE\",
  \"check_interval_sec\": $SUPERVISOR_CHECK_SEC,
  \"stale_timeout_sec\": $SUPERVISOR_STALE_SEC,
  \"task_status_file\": \"$TASK_STATUS_FILE\",
  \"heartbeat_file\": \"$HEARTBEAT_FILE\",
  \"latest_round_log\": \"$latest_round_log\",
  \"task_status_mtime\": \"$task_mtime\",
  \"heartbeat_mtime\": \"$heartbeat_mtime\",
  \"round_log_mtime\": \"$round_mtime\"
}" > "$STATE_FILE" || true
}

cleanup() {
  log "shutdown requested (reason=$EXIT_REASON)"
  if [[ -f "$CHILD_PID_FILE" ]]; then
    local cpid
    cpid="$(cat "$CHILD_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$cpid" ]] && kill -0 "$cpid" 2>/dev/null; then
      kill -TERM "$cpid" 2>/dev/null || true
      sleep 1
      kill -KILL "$cpid" 2>/dev/null || true
    fi
  fi
  rm -f "$PID_FILE" "$CHILD_PID_FILE"
  write_state "stopped" "$EXIT_REASON" "" "" "" "" ""
}

trap 'EXIT_REASON="signal_int"; cleanup; exit 0' INT
trap 'EXIT_REASON="signal_term"; cleanup; exit 0' TERM
trap 'cleanup' EXIT

log "supervisor started pid=$$"
write_state "starting" "boot" "" "" "" "" ""

while true; do
  log "launch longrun model=$MODEL approval=$APPROVAL_MODE"
  "$LONGRUN_SCRIPT" "$MODEL" "$APPROVAL_MODE" >> "$LOG_FILE" 2>&1 &
  CHILD_PID=$!
  echo "$CHILD_PID" > "$CHILD_PID_FILE"

  LAST_ACTIVITY_TS="$(date +%s)"

  while kill -0 "$CHILD_PID" 2>/dev/null; do
    sleep "$SUPERVISOR_CHECK_SEC"
    NOW_TS="$(date +%s)"

    TASK_MTIME=0
    [[ -f "$TASK_STATUS_FILE" ]] && TASK_MTIME="$(stat -f %m "$TASK_STATUS_FILE" 2>/dev/null || echo 0)"

    HEARTBEAT_MTIME=0
    [[ -f "$HEARTBEAT_FILE" ]] && HEARTBEAT_MTIME="$(stat -f %m "$HEARTBEAT_FILE" 2>/dev/null || echo 0)"

    LATEST_ROUND_LOG="$(ls -t "$LONGRUN_LOG_DIR"/round_*.log 2>/dev/null | head -n 1 || true)"
    ROUND_MTIME=0
    [[ -n "$LATEST_ROUND_LOG" && -f "$LATEST_ROUND_LOG" ]] && ROUND_MTIME="$(stat -f %m "$LATEST_ROUND_LOG" 2>/dev/null || echo 0)"

    if [[ "$TASK_MTIME" -gt 0 || "$HEARTBEAT_MTIME" -gt 0 || "$ROUND_MTIME" -gt 0 ]]; then
      LAST_ACTIVITY_TS="$NOW_TS"
      write_state "running" "healthy" "$CHILD_PID" "$LATEST_ROUND_LOG" "$TASK_MTIME" "$HEARTBEAT_MTIME" "$ROUND_MTIME"
      continue
    fi

    STALE_FOR=$((NOW_TS - LAST_ACTIVITY_TS))
    if [[ "$STALE_FOR" -ge "$SUPERVISOR_STALE_SEC" ]]; then
      EXIT_REASON="stale_timeout"
      log "stale detected (${STALE_FOR}s) -> restart child pid=$CHILD_PID"
      write_state "restarting" "stale_timeout" "$CHILD_PID" "$LATEST_ROUND_LOG" "$TASK_MTIME" "$HEARTBEAT_MTIME" "$ROUND_MTIME"
      kill -TERM "$CHILD_PID" 2>/dev/null || true
      sleep 1
      kill -KILL "$CHILD_PID" 2>/dev/null || true
      break
    fi

    write_state "running" "waiting_progress" "$CHILD_PID" "$LATEST_ROUND_LOG" "$TASK_MTIME" "$HEARTBEAT_MTIME" "$ROUND_MTIME"
  done

  wait "$CHILD_PID" || true
  EXIT_REASON="child_exit"
  log "child exited; restart after 3s"
  write_state "restarting" "child_exit" "$CHILD_PID" "" "" "" ""
  sleep 3
done

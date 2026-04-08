#!/bin/zsh
set -euo pipefail

NEXUS_ROOT="."
SRC_MANIFEST="$NEXUS_ROOT/task_manifest.longrun.yaml"
DST_MANIFEST="$NEXUS_ROOT/task_manifest.yaml"
START_SCRIPT="$NEXUS_ROOT/scripts/ops/start_nexus_gemini.sh"
MODEL="${1:-gemini-3-flash-preview}"
APPROVAL_MODE="${2:-yolo}"
SLEEP_BETWEEN_ROUNDS="${SLEEP_BETWEEN_ROUNDS:-5}"
ROUND_TIMEOUT_SEC="${ROUND_TIMEOUT_SEC:-5400}"
AUTO_MODEL_FALLBACK="${AUTO_MODEL_FALLBACK:-1}"
STALE_TIMEOUT_SEC="${STALE_TIMEOUT_SEC:-1800}"
CHECK_INTERVAL_SEC="${CHECK_INTERVAL_SEC:-15}"
HEARTBEAT_FILE="${HEARTBEAT_FILE:-$NEXUS_ROOT/docs/EXEC_LIVE_STATUS.md}"
PROGRESS_FILE="${PROGRESS_FILE:-$NEXUS_ROOT/.nexus/task_status.json}"
LOG_DIR="$NEXUS_ROOT/.nexus/longrun_logs"
CURRENT_MODEL="$MODEL"

[[ -x "$START_SCRIPT" ]] || { echo "Missing launcher: $START_SCRIPT" >&2; exit 1; }
mkdir -p "$LOG_DIR"

if [[ -f "$SRC_MANIFEST" ]]; then
  cp "$SRC_MANIFEST" "$DST_MANIFEST"
fi

echo "[longrun] model=$MODEL approval=$APPROVAL_MODE sleep=${SLEEP_BETWEEN_ROUNDS}s timeout=${ROUND_TIMEOUT_SEC}s stale_timeout=${STALE_TIMEOUT_SEC}s auto_fallback=${AUTO_MODEL_FALLBACK}"

while true; do
  [[ -f "$SRC_MANIFEST" ]] && cp "$SRC_MANIFEST" "$DST_MANIFEST"

  ROUND_TS="$(date '+%Y%m%d_%H%M%S')"
  ROUND_LOG="$LOG_DIR/round_${ROUND_TS}.log"
  echo "[longrun] Starting round at $(date '+%Y-%m-%d %H:%M:%S')"
  echo "[longrun] round_log=$ROUND_LOG"

  set +e
  "$START_SCRIPT" "$CURRENT_MODEL" "$APPROVAL_MODE" > >(tee "$ROUND_LOG") 2>&1 &
  CHILD_PID=$!
  ROUND_START_TS=$(date +%s)
  LAST_ACTIVITY_TS=$ROUND_START_TS
  LAST_PROGRESS_MTIME=0
  LAST_HEARTBEAT_MTIME=0
  LAST_LOG_SIZE=0

  while kill -0 "$CHILD_PID" 2>/dev/null; do
    sleep "$CHECK_INTERVAL_SEC"
    NOW_TS=$(date +%s)

    if [[ -f "$PROGRESS_FILE" ]]; then
      CUR_PROGRESS_MTIME=$(stat -f %m "$PROGRESS_FILE" 2>/dev/null || echo 0)
      if [[ "$CUR_PROGRESS_MTIME" -gt "$LAST_PROGRESS_MTIME" ]]; then
        LAST_PROGRESS_MTIME="$CUR_PROGRESS_MTIME"
        LAST_ACTIVITY_TS="$NOW_TS"
      fi
    fi

    if [[ -f "$HEARTBEAT_FILE" ]]; then
      CUR_HEARTBEAT_MTIME=$(stat -f %m "$HEARTBEAT_FILE" 2>/dev/null || echo 0)
      if [[ "$CUR_HEARTBEAT_MTIME" -gt "$LAST_HEARTBEAT_MTIME" ]]; then
        LAST_HEARTBEAT_MTIME="$CUR_HEARTBEAT_MTIME"
        LAST_ACTIVITY_TS="$NOW_TS"
      fi
    fi

    if [[ -f "$ROUND_LOG" ]]; then
      CUR_LOG_SIZE=$(wc -c < "$ROUND_LOG" 2>/dev/null || echo 0)
      if [[ "$CUR_LOG_SIZE" -gt "$LAST_LOG_SIZE" ]]; then
        LAST_LOG_SIZE="$CUR_LOG_SIZE"
        LAST_ACTIVITY_TS="$NOW_TS"
      fi
    fi

    ELAPSED=$((NOW_TS - ROUND_START_TS))
    STALE_FOR=$((NOW_TS - LAST_ACTIVITY_TS))

    if [[ "$ELAPSED" -ge "$ROUND_TIMEOUT_SEC" ]]; then
      echo "[longrun] watchdog timeout: elapsed=${ELAPSED}s >= ${ROUND_TIMEOUT_SEC}s, terminating child pid=$CHILD_PID"
      kill -TERM "$CHILD_PID" 2>/dev/null || true
      sleep 1
      kill -KILL "$CHILD_PID" 2>/dev/null || true
      break
    fi

    if [[ "$STALE_FOR" -ge "$STALE_TIMEOUT_SEC" ]]; then
      echo "[longrun] watchdog stale: no activity for ${STALE_FOR}s (heartbeat/task_status/log), terminating child pid=$CHILD_PID"
      kill -TERM "$CHILD_PID" 2>/dev/null || true
      sleep 1
      kill -KILL "$CHILD_PID" 2>/dev/null || true
      break
    fi
  done

  wait "$CHILD_PID"
  RC=$?
  set -e

  echo "[longrun] Round exited rc=$RC at $(date '+%Y-%m-%d %H:%M:%S')"
  if [[ "$AUTO_MODEL_FALLBACK" == "1" ]] && [[ "$RC" -ne 0 ]] && grep -q "exhausted your capacity on this model" "$ROUND_LOG"; then
    if [[ "$CURRENT_MODEL" == "gemini-3.1-pro-preview" ]]; then
      CURRENT_MODEL="gemini-3-flash-preview"
      echo "[longrun] auto-switch model: pro -> flash (quota exhausted)"
    else
      CURRENT_MODEL="gemini-3.1-pro-preview"
      echo "[longrun] auto-switch model: flash -> pro (quota exhausted)"
    fi
  fi

  sleep "$SLEEP_BETWEEN_ROUNDS"
done

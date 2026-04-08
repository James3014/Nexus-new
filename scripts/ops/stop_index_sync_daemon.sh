#!/bin/zsh
REPO_ROOT="."
PID_FILE="$REPO_ROOT/.nexus/task_scheduler.pid"

if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  echo "⏹️ [Nexus] Stopping Task Scheduler (PID: $PID)..."
  kill "$PID" 2>/dev/null || pkill -f task_scheduler.py
  rm -f "$PID_FILE"
  echo "✅ STOPPED"
  nohup say "自動化執行器已停止" > /dev/null 2>&1 &
else
  pkill -f task_scheduler.py
  echo "[!] PID file not found, performed pkill."
fi

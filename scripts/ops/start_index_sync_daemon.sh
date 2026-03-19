#!/bin/zsh
REPO_ROOT="/Users/jameschen/Workspace/nexus"
PID_FILE="$REPO_ROOT/.nexus/task_scheduler.pid"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[!] Scheduler already running (PID: $OLD_PID)"
    exit 0
  fi
fi

cd "$REPO_ROOT"
nohup uv run python scripts/ops/task_scheduler.py > .nexus/task_scheduler.log 2>&1 &
echo $! > "$PID_FILE"
echo "🚀 [Nexus] Task Scheduler started in background (PID: $!)"
nohup say "自動化執行器已啟動" > /dev/null 2>&1 &

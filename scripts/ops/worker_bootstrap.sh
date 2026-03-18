#!/bin/zsh
set -euo pipefail

WORKER_ID="${1:-worker-1}"
MODEL="${2:-gemini-3-flash-preview}"
NEXUS_ROOT="/Users/jameschen/Workspace/nexus"
WORKTREE_DIR="$NEXUS_ROOT/worktrees/$WORKER_ID"
STATUS_FILE="$NEXUS_ROOT/.nexus/worker_status_${WORKER_ID}.json"

echo "[$WORKER_ID] Initializing with model=$MODEL"
mkdir -p "$NEXUS_ROOT/.nexus"

# 模型切換邏輯 (Flash -> Pro)
run_with_retry() {
    local CURRENT_MODEL="$MODEL"
    set +e
    echo "[$WORKER_ID] Running runner for task list..."
    # 執行 Nexus Runner
    NEXUS_MODEL="$CURRENT_MODEL" NEXUS_RELAXED_GATE=1 \
    uv run scripts/engine/nexus_cli.py nexus:runner --worker "$WORKER_ID"
    RC=$?
    set -e

    if [[ "$RC" -ne 0 && "$CURRENT_MODEL" == "gemini-3-flash-preview" ]]; then
        echo "[$WORKER_ID] switch: flash -> pro | reason=failure_fallback"
        NEXUS_MODEL="gemini-3.1-pro-preview" NEXUS_RELAXED_GATE=1 \
        uv run scripts/engine/nexus_cli.py nexus:runner --worker "$WORKER_ID"
        RC=$?
    fi
    return "$RC"
}

# 回報生成
echo "{\"worker_id\": \"$WORKER_ID\", \"status\": \"started\", \"ts\": \"$(date)\"}" > "$STATUS_FILE"

run_with_retry
RC=$?

if [[ "$RC" -eq 0 ]]; then
    echo "{\"worker_id\": \"$WORKER_ID\", \"status\": \"done\", \"rc\": 0, \"ts\": \"$(date)\"}" > "$STATUS_FILE"
    nohup say "$WORKER_ID 任務完成" > /dev/null 2>&1 &
else
    echo "{\"worker_id\": \"$WORKER_ID\", \"status\": \"failed\", \"rc\": $RC, \"ts\": \"$(date)\"}" > "$STATUS_FILE"
    nohup say "$WORKER_ID 任務失敗" > /dev/null 2>&1 &
fi

exit "$RC"

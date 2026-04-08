#!/bin/zsh
set -euo pipefail

NEXUS_ROOT="."
WORKTREE_BASE="$NEXUS_ROOT/worktrees"
WORKERS=("worker-1" "worker-2" "worker-3" "worker-4")
DEFAULT_MODEL="gemini-3-flash-preview"

mkdir -p "$WORKTREE_BASE"
mkdir -p "$NEXUS_ROOT/.nexus"

echo "[Orchestrator] Starting Index-Driven Parallel Execution (ERA-C)"
echo "[Orchestrator] Single Commander Mode: Active"

# Step 1: 解析 INDEX 並同步 Manifest
echo "[Orchestrator] Parsing docs/INDEX.md -> task_manifest.yaml"
uv run scripts/ops/index_to_manifest.py

# Step 2: 建立平行工作區 (Git Worktrees)
echo "[Orchestrator] Deploying 4 Workers in Parallel..."
for WORKER in "${WORKERS[@]}"; do
    TARGET_DIR="$WORKTREE_BASE/$WORKER"
    
    # 清理舊的 Worktree (安全起見)
    if [[ -d "$TARGET_DIR" ]]; then
        echo "  [!] Cleaning up existing worktree: $WORKER"
        git worktree remove -f "$TARGET_DIR" || true
        rm -rf "$TARGET_DIR"
    fi
    
    # 建立新的 Worktree
    echo "  [+] Creating Worktree for $WORKER at $TARGET_DIR"
    git worktree add -B "branch-$WORKER" "$TARGET_DIR" main
    
    # 複製啟動腳本與必要文件 (Symlink)
    ln -sf "$NEXUS_ROOT/scripts/ops/worker_bootstrap.sh" "$TARGET_DIR/worker_bootstrap.sh"
done

# Step 3: 並行啟動分身
# 注意: Worker 4 (Secretary) 會受 depends_on 控制，所以在這裡啟動也是安全的
for WORKER in "${WORKERS[@]}"; do
    echo "  [RUN] Launching $WORKER in background..."
    nohup "$WORKTREE_BASE/$WORKER/worker_bootstrap.sh" "$WORKER" "$DEFAULT_MODEL" > "$NEXUS_ROOT/.nexus/worker_${WORKER}.log" 2>&1 &
done

echo "[Orchestrator] All workers launched. Monitoring progress..."
echo "[Orchestrator] Watch EXEC_LIVE_STATUS.md for updates."

# 定時輪詢合併回報 (簡易版)
while true; do
    COMPLETED_COUNT=0
    for WORKER in "${WORKERS[@]}"; do
        if [[ -f "$NEXUS_ROOT/.nexus/worker_status_${WORKER}.json" ]]; then
            STATUS=$(grep -o '"status": "[^"]*"' "$NEXUS_ROOT/.nexus/worker_status_${WORKER}.json" | cut -d'"' -f4)
            if [[ "$STATUS" == "done" || "$STATUS" == "failed" ]]; then
                ((COMPLETED_COUNT++))
            fi
        fi
    done

    if [[ "$COMPLETED_COUNT" -eq 4 ]]; then
        echo "[Orchestrator] All workers finished. Performing Final Gate..."
        break
    fi
    sleep 10
done

# Final Milestone: 指派 Worker-4 完成最後的 INDEX 同步
echo "[Orchestrator] Finalizing: Worker-4 writing back to docs/INDEX.md..."
uv run scripts/engine/nexus_cli.py nexus:runner --task docs.index.sync

echo "[Orchestrator] --- BATCH COMPLETED ---"
echo "SUMMARY / METRICS / GATE / EVIDENCE_PATHS / NEXT"

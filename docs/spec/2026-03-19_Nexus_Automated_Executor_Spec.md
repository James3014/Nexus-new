# Nexus Automated Executor (L2 Autonomous) - Build Spec v1.0

## 1. Executive Summary
Nexus 自動化執行器標誌著系統從「被動腳本」演化為「主動生命體」。它具備掃描 `INDEX.md` 指令、調度 `worktree` 分身、監控 `phase_health` 痛覺以及自動修補代碼的能力。

## 2. State Transition & Lifecycle
- **IDLE**: 監控並等待 `INDEX.md` 或 `task_manifest.yaml` 的異動。
- **PLANNING (Manifest Sync)**: 解析文件並計算 DAG 依賴。
- **EXECUTION (Fan-out)**: 調用 `git worktree`，將任務分發至 4 個並行 Worker。
- **AUDIT (Gate Keeper)**: 收集 Worker 回報，執行 `ci_gate.py` 全局檢查。
- **REPAIR (Self-Healing)**: 偵測到 `Health < 88` 時，暫停一般任務鏈，注入 `auto.repair` 專項。
- **REPORT (Sync Back)**: 將最終儀表板數據寫回 Obsidian。

## 3. JSON Schema Contracts (Task Pulse)
```json
{
  "executor_id": "nexus-cex-01",
  "active_workers": ["worker-1", "worker-3"],
  "global_health": 95.4,
  "last_healing_event": "auto.repair.proto@2026-03-19_1015",
  "learning_velocity": +0.02
}
```

## 4. Mechanized Safeguards
- **Stalled Detection**: 超過 1800 秒無 Heartbeat 寫入，強制重啟該 Worker 工作區。
- **Worktree Isolation**: 每個分身有獨立磁碟路徑，互不影響 Patch 寫入感度。

## 5. Deployment
- 指令：`uv run scripts/ops/task_scheduler.py --mode autonomous`

---
*Created by Antigravity - 2026-03-19*

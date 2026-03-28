# Nexus 自癒系統研究交接包（給研究 Agent）

## 1. 研究目標
- 目標：提升 Nexus 自癒能力，優先改善 `C` 相位學習分數與跨輪修復命中率。
- 現況：流程可運作、六相位可量測、`high` 檢查已通過，但 `C` 分數仍偏中段。

## 2. 最新真實數據（請先看）
- 高標自檢輸出：`/Users/jameschen/Workspace/nexus/.nexus/runs/task-1774606410/self_check_high.csv`
- 關鍵值（OFF-001）：
  - `health`: `91.0`（PASS）
  - `phase_path`: `P -> X -> D -> R -> A -> C`
  - `phase_health_c`: `74.5`
  - `phase_signal_status_c`: `measured`
- 解讀：C 已不是「未量測」或「假低分」，而是學習訊號品質不足導致偏低。

## 3. 核心程式碼入口（必讀）
- 評分與訊號
  - `/Users/jameschen/Workspace/nexus/nexus/health/scoring.py`
  - `/Users/jameschen/Workspace/nexus/nexus/health/signals.py`
- 自癒主循環
  - `/Users/jameschen/Workspace/nexus/nexus/health/service.py`
  - `/Users/jameschen/Workspace/nexus/nexus/health/policy.py`
  - `/Users/jameschen/Workspace/nexus/nexus/health/planner.py`
  - `/Users/jameschen/Workspace/nexus/nexus/health/executor.py`
  - `/Users/jameschen/Workspace/nexus/nexus/health/ops.py`
- 流程與狀態機
  - `/Users/jameschen/Workspace/nexus/nexus/engine/pipeline.py`
  - `/Users/jameschen/Workspace/nexus/nexus/core/commander.py`
  - `/Users/jameschen/Workspace/nexus/nexus/core/policy_manager.py`
  - `/Users/jameschen/Workspace/nexus/nexus/core/state_contracts.py`
- 健康報表輸出
  - `/Users/jameschen/Workspace/nexus/nexus/engine/coordinator.py`
  - `/Users/jameschen/Workspace/nexus/scripts/ops/write_phase_metrics.py`
  - `/Users/jameschen/Workspace/nexus/scripts/ops/ci_gate.py`

## 4. 已知關鍵事實（避免重複踩坑）
- `C` 低分曾由時序 bug 造成：
  - `record_episode()` 過早執行，把成功誤判為失敗。
  - `Commander` 讀舊 state，導致 `C` 指標退回保守值。
- 上述時序問題已修正，現在 `C=74.5` 是真實分數，不是 bug 幻象。

## 5. 研究方向（優先順序）
- 優先 A：把 `lesson_quality` 從固定值升級為「證據型評分」
  - 輸入候選：回歸成功率、重試次數、修補範圍漂移、審計穩定度。
- 優先 B：建立跨 run 的 `next_run_hit_rate` 真實回饋
  - 不是單輪估算，改為「下一輪是否命中且成功」的閉環統計。
- 優先 C：提升 `policy_hit` 命中密度
  - 針對高頻故障簽名做策略聚類，降低「空命中」。

## 6. 可直接執行的驗證指令
- 單次高標自檢：
  - `cd /Users/jameschen/Workspace/nexus && uv run scripts/engine/nexus_cli.py nexus:check --level high`
- 自癒 dry-run / 標準 / 嚴格：
  - `cd /Users/jameschen/Workspace/nexus && uv run scripts/engine/nexus_cli.py nexus:self-heal --mode dry-run`
  - `cd /Users/jameschen/Workspace/nexus && uv run scripts/engine/nexus_cli.py nexus:self-heal --mode standard`
  - `cd /Users/jameschen/Workspace/nexus && uv run scripts/engine/nexus_cli.py nexus:self-heal --mode strict`
- 目前回歸基準（已通過）：
  - `cd /Users/jameschen/Workspace/nexus && uv run pytest tests/health tests/test_engine_coordinator.py tests/test_phantom_success_guards.py tests/benchmark/test_workspace.py -q`

## 7. 研究 agent 權限邊界（建議）
- 可改：
  - `nexus/health/*`
  - `nexus/core/policy_manager.py`
  - `nexus/engine/pipeline.py`
  - 對應 `tests/health/*` 與 `tests/test_phantom_success_guards.py`
- 不建議先動：
  - `scripts/nexus_pilot_*`（CLI 對外體驗主線）
  - 與朋友交付入口相關腳本

## 8. 通知機制補充
- `audio-notify` 已改為可選 fallback（不再因缺檔噴錯）：
  - 優先 `NEXUS_AUDIO_NOTIFY_SCRIPT`
  - 次選既有預設 `notify.py`（存在才用）
  - 再次選系統 `say`
  - 都不可用則靜默略過
- 關閉通知：`NEXUS_AUDIO_NOTIFY=0`

## 9. 最小交付定義（給研究 agent）
- `high check` 連續 3 次 PASS。
- 六相位皆 `measured`。
- `phase_health_c` 平均 >= 75（至少不低於 70）。
- 不得引入新旁路或降級成假訊號加分。

# Nexus Phase Health Implementation Plan (v1)

> [!important]
> **Status**: `COMPLETED` / `ERA-C` (2026-03-19)

## Scope
目標是把以下 5 項變成可直接執行的工程任務：
1. `phase_health` 落檔（六階段可量測）
2. `auto.repair.on_low_health`
3. `learning_velocity` + `auto.optimize.on_low_learning`
4. `ci_gate` 新增 `lowest_phase_health` 與 `learning_velocity`
5. 維持 `raw token > 0` 真實審計模式

## Current Baseline (2026-03-18)
- `ci_gate`: PASS
- `success_rate`: 100%
- `avg_health`: 92.95
- `lowest_phase_health`: 80.0
- `total_raw_tokens`: 0
- `token_mode`: estimate

## Progress Snapshot (2026-03-18 20:19 Asia/Taipei)
- `WP-1`: DONE（phase metrics + learning velocity + sparkline + gate summary）
- `WP-2`: DONE（STRICT 90/80 門檻通過）
- `auto.repair`：注入已驗證，但存在 `blocked` 原型案例（需在 WP-3 收斂至少 1 輪為 done）
- `WP-3`: READY FOR HANDOFF（由新 agent 接手）

## Work Breakdown

### WP-1: Phase Metrics Foundation (P0)
- Files
  - `nexus/engine/pipeline.py`
  - `nexus/core/orchestrator.py`
  - `scripts/ops/task_runner.py`
- Deliverables
  - `.nexus/runs/<run_id>/phase_metrics.json`
  - 每個 phase 產出：`phase`, `health`, `signals`, `timestamp`
- Acceptance
  - 六個 phase (`P/X/D/R/A/C`) 皆有 `health`
  - 缺任一 phase 則 gate 失敗

### WP-2: Auto Repair on Low Health (P0)
- Files
  - `scripts/ops/task_runner.py`
  - `task_manifest.yaml`
- Trigger
  - 任一 `phase_health < 85` 連續兩輪
  - 或 `pipeline_health < 88`
- Behavior
  - 動態注入 `auto.repair.<phase>`
  - `max_retry: 2`, 失敗 `on_fail: escalate`
- Acceptance
  - 測試可觸發 repair 任務
  - repair 後 health 回升或有明確 escalate 證據

### WP-3: Learning Velocity + Auto Optimize (P1)
- Files
  - `scripts/ops/ci_gate.py`
  - `nexus/core/orchestrator.py`
  - `task_manifest.yaml`
- Computation Window
  - 最近 3 輪
- Inputs
  - `success_rate`, `avg_health`, `retry_count`, `token_per_task`
- Trigger
  - `learning_velocity <= 0` 連續三輪
- Behavior
  - 注入 `auto.optimize.on_low_learning`
  - 執行 router 權重微調 + context 剪枝
- Acceptance
  - 下一輪至少 1 項改善（success/health/retry/token）
  - `auto.repair` blocked 原型至少收斂 1 輪為 `done`，確認自治閉環

### WP-4: CI Gate Summary Upgrade (P1)
- Files
  - `scripts/ops/ci_gate.py`
  - `docs/EXEC_LIVE_STATUS.md`
- New Fields
  - `lowest_phase_health`
  - `learning_velocity`
  - `raw_token_mode` (`real|estimate`)
- Acceptance
  - 每輪 gate 輸出固定帶上述欄位

### WP-5: Token Mode Governance (P0)
- Rule
  - `total_raw_tokens > 0` => `raw_token_mode=real`
  - `total_raw_tokens == 0` => `raw_token_mode=estimate`
- Files
  - `docs/INDEX.md`
  - `docs/EXEC_LIVE_STATUS.md`
- Acceptance
  - 文件口徑與 gate 輸出一致，無自相矛盾敘述

## Task Manifest Pack (Ready to import)
```yaml
- id: phase.metrics.foundation
  depends_on: []
  run: "uv run pytest -q tests -k 'phase_health or phase_metrics' --maxfail=1"
  done_when:
    type: command_rc_zero
  on_fail: retry
  max_retry: 1
  ask_policy: no_ask

- id: auto.repair.on_low_health
  depends_on: [phase.metrics.foundation]
  run: "uv run scripts/engine/nexus_cli.py nexus:runner"
  done_when:
    type: command_rc_zero
  on_fail: escalate
  max_retry: 2
  ask_policy: no_ask

- id: learning.velocity.enable
  depends_on: [auto.repair.on_low_health]
  run: "uv run pytest -q tests -k 'learning_velocity' --maxfail=1"
  done_when:
    type: command_rc_zero
  on_fail: retry
  max_retry: 1
  ask_policy: no_ask

- id: auto.optimize.on_low_learning
  depends_on: [learning.velocity.enable]
  run: "uv run scripts/engine/nexus_cli.py nexus:runner"
  done_when:
    type: command_rc_zero
  on_fail: escalate
  max_retry: 1
  ask_policy: no_ask

- id: gate.summary.upgrade
  depends_on: [auto.optimize.on_low_learning]
  run: "uv run scripts/ops/ci_gate.py"
  done_when:
    type: command_rc_zero
  on_fail: retry
  max_retry: 1
  ask_policy: no_ask
```

## Reporting Contract
每輪回報固定：
- SUMMARY
- METRICS (`success_rate`, `avg_health`, `lowest_phase_health`, `learning_velocity`, `total_raw_tokens`)
- GATE
- EVIDENCE_PATHS
- NEXT

## WP-3 Handoff Contract (for next agent)
1. 不得回退 WP-1/WP-2 已驗收行為。
2. 預設以 STRICT 模式驗收（未明示需求不得開 `NEXUS_RELAXED_GATE=1`）。
3. 任務入口固定：`uv run scripts/nexus_cli.py nexus:runner`。
4. 最終回報格式固定：`SUMMARY / METRICS / GATE / EVIDENCE_PATHS / NEXT`。


## Detailed Specifications (PI-Series)

### PI-1: 動態閾值調校 (P25 分位 + 安全欄 ±4)
- **演算法**: 每 10 輪統計一次 `ci_benchmark.csv` 的歷史數據。
- **計算門檻**: `Dynamic_Threshold = max(Minimum_Base, percentile(history_health, 25))`
- **安全約束**: 每次調整幅度不得超過 `±4` 分，防止極端樣本導致門檻劇烈波動。
- **目標**: 實現在高基準（如 98 分）下自動提升靈敏度，在低基準下恢復韌性。

### PI-2: C 階段 crystal_reuse_rate 量化公式與來源
- **數據來源**:
  - `router_decisions.jsonl` 中的 `selected_skill` 是否與 Crystal Cache 命中。
  - `state.skills_used` 中的 `reused_flag`。
- **量化公式**: `crystal_reuse_rate = (Heuristic_Hits + Skill_Repeat_Hits) / Total_Task_Count`
- **整合點**: 作為 `C.health` 的核心分量，反映 Nexus 對過往經驗的吸收程度。

### PI-3: learning_velocity 趨勢折線 (sparkline) 規格
- **顯示位置**: `ci_gate` 摘要底部 & `EXEC_LIVE_STATUS.md`。
- **渲染規格**: 採用 ASCII Sparkline `[ ▃▅▆▇]` 表示最近 10 個任務的 `pipeline_health` 變動率。
- **意義**: 向上折線代表 Nexus 正進入「上升學習區」，向下則觸發 `auto.optimize` 預判。


## Task Manifest Pack (Instrumentation v1.1)
```yaml
- id: health_metrics_writer
  depends_on: [gate.ci]
  run: "uv run python scripts/ops/write_phase_metrics.py"
  done_when:
    type: command_rc_zero
  on_fail: retry
  max_retry: 1
  ask_policy: no_ask
  evidence_paths:
    - .nexus/runs/latest/phase_metrics.json

- id: velocity_calculator_and_sparkline
  depends_on: [health_metrics_writer]
  run: "uv run python scripts/ops/calc_learning_velocity.py --window 3 && uv run python scripts/ops/render_phase_sparkline.py --window 3"
  done_when:
    type: command_rc_zero
  on_fail: retry
  max_retry: 1
  ask_policy: no_ask
  evidence_paths:
    - .nexus/learning_velocity.json
    - docs/EXEC_LIVE_STATUS.md

- id: gate.summary_with_velocity
  depends_on: [velocity_calculator_and_sparkline]
  run: "uv run scripts/ops/ci_gate.py"
  done_when:
    type: command_rc_zero
  on_fail: retry
  max_retry: 1
  ask_policy: no_ask
  evidence_paths:
    - ci_benchmark.csv
    - docs/EXEC_LIVE_STATUS.md
```

## Acceptance Snapshot (Instrumentation v1.1)
- 輸出 `phase_metrics.json`（六階段）
- 輸出 `learning_velocity` 與 sparkline
- `ci_gate` 摘要包含 `lowest_phase_health`、`learning_velocity`

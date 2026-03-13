# Muse-Nexus Refactor Roadmap

## Goal

在不破壞現有成熟腳本的前提下，把 Muse-Nexus 從 script-driven system 演進成 contract-driven workflow system。

## Migration Strategy

建議把這次升級視為一個獨立 Muse 任務，在新 worktree 中完成，而不是直接在主工作樹混改。

兩輪策略：

1. Internal first
   - 先上 contracts、Context Hub、Reflection、skills router skeleton
   - X / Felo 先只打 flag，不真的呼叫外部
2. External second
   - 等 internal path 穩定後，再接 `research_pack.json` 與 Felo / external routing

Execution priority:

1. migration safety validator
2. state contracts
3. skills router prototype
4. Context Hub + repair integration
5. external routing

## Phase 1: State Contracts First

Deliverables:

- `.muse_state/` 目錄結構
- `schema_version`
- `current_phase`
- `current_step_id`
- `steps_history`
- `plan.json`
- `diagnosis.json`
- `reflection.jsonl`
- `skills_used.json`
- `repair_rounds.jsonl`
- `repair_final.json`
- `audit_result.json`
- `trace_log.jsonl`

Why first:

- 沒有 contract，就沒有穩定 orchestration
- 沒有 state，就很難做 war room、回放、handoff
- 沒有 contract，也無法讓 gatekeeper validator 穩定驗證

Phase gate:

- 進入後續 phase 前，`migration_safety_validator.py --mode gatekeeper` 應先通過

## Phase 2: Extract Context Hub

Deliverables:

- `context_hub.py`
- `diag_context_pack.json`
- `repair_context_pack.json`
- `audit_context_pack.json`

Context policy:

- 由 Context Hub 統一決定是否需要 external research
- 由 Context Hub 觸發 skills router
- 由 Context Hub 決定哪些 arrays 可在 prompt 端轉成 TOON 視圖

Migration rule:

- 先把既有 context assembly 從 `codex_loop_brain.py` 拆出去
- 不急著改業務邏輯，只先改輸入出口
- TOON 只作為 prompt serialization，不改 state contract

## Phase 3: Shrink Codex Loop into Repair Engine

Deliverables:

- `repair_engine.py`
- 清楚的 round result output
- reflection round write path

Migration rule:

- 保留 patch / test / retry loop
- 移除它對 plan / lessons / drift / memory 的直接拼裝責任
- 預留 `external_needed` hook，但第一輪可先不真的查外部

## Phase 4: Add Commander CLI

Deliverables:

- `commander.py`
- 同步 CLI orchestration flow
- phase / step state updates
- skills router invocation point

Expected flow:

```text
commander
  -> plan
  -> diag
  -> optional research
  -> repair
  -> audit
  -> crystal
```

## Phase 5: Add External Research Router

Deliverables:

- `research_router.py`
- `research_pack.json`

Rule:

- 預設不查外部
- 只有第三方依賴 / 高不確定 / reviewer 明示要求時才啟動
- Felo 失敗時必須 fallback 到 internal-only mode

## Phase 6: Add Skills Router

Deliverables:

- `skills_router.py`
- phase-based routing table
- task metadata to skill selection rules
- state write-back rules

Rule:

- 不把 skill 行為硬寫進 system prompt
- 由 phase + task type + state 決定 skill 啟用
- skills 輸出必須回寫 `.muse_state`，讓 phase 腳本只吃 contract
- 第一版先用 decision tree + scorecard prototype，不急著做自動調權

## Compatibility Rules

- schema 升級盡量 append fields，不改既有 key 語義
- 舊 trace / 舊 task 在 viz 中必須能 `.get(..., default)` 安全讀取
- 第一輪可先讓新欄位只對新任務出現，legacy task best-effort 顯示

## Performance Guardrails

- internal-only path 的 token overhead 目標小於舊版基準 `1.2x`
- migration slice latency 應保留 baseline 與對照值
- 若超過 20% overhead，需在驗收與回報中明確標記原因

## Recommended Implementation Order

1. contracts
2. reflection / steps / skills fields
3. context hub
4. repair engine extraction
5. diag / audit hook points
6. commander
7. viz compatibility
8. research router
9. skills router full routing

## Anti-Pattern To Avoid

- 一開始就重寫全部腳本
- 先做 GUI，再做 contract
- 先接很多外部工具，再穩定 state model
- 讓 `codex_loop_brain.py` 繼續膨脹
- 在 X / Felo 尚未穩定前把外部路由寫死
- 讓 TOON 進入權威 state 或 contract 層

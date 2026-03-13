# Muse-Nexus Refactor Roadmap

## Goal

在不破壞現有成熟腳本的前提下，把 Muse-Nexus 從 script-driven system 演進成 contract-driven workflow system。

## Phase 1: State Contracts First

Deliverables:

- `.muse_state/` 目錄結構
- `plan.json`
- `diagnosis.json`
- `repair_rounds.jsonl`
- `repair_final.json`
- `audit_result.json`
- `trace_log.jsonl`

Why first:

- 沒有 contract，就沒有穩定 orchestration
- 沒有 state，就很難做 war room、回放、handoff

## Phase 2: Extract Context Hub

Deliverables:

- `context_hub.py`
- `diag_context_pack.json`
- `repair_context_pack.json`
- `audit_context_pack.json`

Migration rule:

- 先把既有 context assembly 從 `codex_loop_brain.py` 拆出去
- 不急著改業務邏輯，只先改輸入出口

## Phase 3: Shrink Codex Loop into Repair Engine

Deliverables:

- `repair_engine.py`
- 清楚的 round result output

Migration rule:

- 保留 patch / test / retry loop
- 移除它對 plan / lessons / drift / memory 的直接拼裝責任

## Phase 4: Add Commander CLI

Deliverables:

- `commander.py`
- 同步 CLI orchestration flow

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

## Phase 6: Add Skills Router

Deliverables:

- `skills_router.py`
- phase-based routing table

Rule:

- 不把 skill 行為硬寫進 system prompt
- 由 phase + task type + state 決定 skill 啟用

## Recommended Implementation Order

1. contracts
2. trace ledger
3. context hub
4. commander
5. repair engine extraction
6. audit engine unification
7. crystal alignment
8. research router
9. skills router

## Anti-Pattern To Avoid

- 一開始就重寫全部腳本
- 先做 GUI，再做 contract
- 先接很多外部工具，再穩定 state model
- 讓 `codex_loop_brain.py` 繼續膨脹

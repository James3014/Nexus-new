# Muse-Nexus Target Architecture

## Target Definition

目標中的 Muse-Nexus 是一個以 coding workflow 為核心的 orchestration system，主軸為：

- Commander
- Context Hub
- P-D-X-R-A-C workflow
- `.muse_state` state snapshot
- trace ledger
- skills router

## High-Level Shape

```text
Intent
  -> Commander
  -> Plan
  -> Diag
  -> External Research (optional)
  -> Repair
  -> Audit
  -> Crystal
  -> lessons / memory
```

## Core Components

### Commander

Role:

- 任務入口與 phase orchestrator
- 建立 worktree
- 維護 `.muse_state`
- 寫入 `trace_log.jsonl`
- 決定 phase 轉移

Commander should not:

- 直接承擔大型 context assembly
- 直接執行 domain-specific patching 邏輯
- 在 prompt 中硬編所有 skills 行為

### Context Hub

Role:

- 依 phase 組裝 context pack
- 聚合：
  - task goal
  - codebase scan
  - Obsidian / LanceDB memory
  - reflection memory
  - external research
  - skills outputs

Key outputs:

- `plan.json`
- `diag_context_pack.json`
- `repair_context_pack.json`
- `audit_context_pack.json`

### P-D-X-R-A-C

#### P: Plan

- 建立 worktree
- 確認 env parity
- 匯入 lessons / negative constraints
- 產出 `plan.json`

#### D: Diag

- 跑 test / smoke / command
- 由 diagnosis engine 產出 `diagnosis.json`
- 視需要請求 X

#### X: External Research

- 僅在外部依賴或高不確定時啟動
- 產出 `research_pack.json`

#### R: Repair

- 多輪 patch / test / reflect loop
- round-by-round 記錄 progress
- 產出 `repair_final.json`

#### A: Audit

- deterministic gates
- reviewer verdicts
- 產出 `audit_result.json`

#### C: Crystal

- 將成功或失敗經驗固化成 lesson
- 更新 memory / lesson pipeline

## Suggested State Layout

```text
.muse_state/
├── plan.json
├── diag_context_pack.json
├── diagnosis.json
├── research_pack.json
├── repair_context_pack.json
├── repair_rounds.jsonl
├── repair_final.json
├── audit_context_pack.json
├── audit_result.json
└── trace_log.jsonl
```

## Architectural Principle

核心原則不是「增加更多 agent」，而是：

> 讓每一個 phase 的輸入、輸出、責任與可回放資料都清晰。

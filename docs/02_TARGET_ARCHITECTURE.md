# Muse-Nexus Target Architecture

## Target Definition

目標中的 Muse-Nexus 是一個以 coding workflow 為核心的 orchestration system，主軸為：

- Commander
- Context Hub
- P-D-X-R-A-C workflow
- `.muse_state` state snapshot
- trace ledger
- skills router
- external research gating
- reflection memory

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

Context Hub also decides:

- 是否需要 external research
- 是否需要呼叫 skills router
- 哪些 large arrays 要在 prompt 端做壓縮視圖

### Skills Router

Role:

- 在每個 phase 執行前，根據 phase 與 task metadata 決定是否啟用 skill
- 將 skill 輸出寫回 `.muse_state` 對應檔案
- 讓 phase 腳本只讀 state，不直接硬呼叫 skills

Typical inputs:

- `phase`
- `task_metadata`
- `failure_signature`
- `language`
- `is_new_feature`
- `is_large_refactor`
- `stacktrace_pattern`

Typical outputs:

- `skills_used`
- `skill_invocations`
- `plan.json.spec_context.*`
- `diag_context_pack.json.hotspots`
- `repair_context_pack.json.code_quality_report`
- `audit_context_pack.json.code_quality`

Routing principle:

- `Skill != Phase`
- phase 決定工作流
- skill 是 phase 的工具箱，由 router 表驅動

### P-D-X-R-A-C

#### P: Plan

- 建立 worktree
- 確認 env parity
- 匯入 lessons / negative constraints
- 產出 `plan.json`

#### D: Diag

- 跑 test / smoke / command
- 由 diagnosis engine 產出 `diagnosis.json`
- 視需要設定 `needs_research`
- 可輸出 `diag_context_pack.json`

#### X: External Research

- 僅在外部依賴或高不確定時啟動
- 產出 `research_pack.json`
- Felo / 外部工具失敗時必須可安全退回 internal-only mode

#### R: Repair

- 多輪 patch / test / reflect loop
- round-by-round 記錄 progress
- 產出 `repair_final.json`
- 寫入 reflection rounds / recent failures / skills_used

#### A: Audit

- deterministic gates
- reviewer verdicts
- 產出 `audit_result.json`
- 僅在 reviewer 明示或 protocol/security 需求時才考慮再進 X

#### C: Crystal

- 將成功或失敗經驗固化成 lesson
- 更新 memory / lesson pipeline

## 🏗️ Factory Scaling (v7 Evolution)

Nexus v7 透過以下組件實現工廠級規模化：

### 🏎️ Factory Router
- **智慧分發**: 基於優先級 (Hotfix Priority 0) 與模型配額 (QPS 節流) 的自動化派發系統。
- **SQLite Queue**: 任務隊列持久化，支援崩潰自癒與任務重啟。

### 🛡️ Batch Guard & WarRoom
- **Session Isolation**: 基於 Tmux 的物理環境隔離，每個任務擁有獨立的 Worktree 與預算鎖。
- **Stalled Detection**: 自動檢測任務停滯並觸發 "Melt" 熔斷機制，保障系統資源不被死鎖占用。

## 🏗️ Factory Scaling (v7 Evolution)

為了支援「夜班工廠」模式，架構擴充了以下組件：

### Factory Router
- **智慧調度**: 優先處理 Hotfix (Priority 0)，並根據模型 Quota (Claude 10RPM / Gemini 20RPM) 進行併發管理。
- **SQLite Queue Manager**: 採用持久化隊列確保任務狀態原子化。

### Batch Guard & Monitor
- **Tmux Isolation**: 每個任務在獨立 Tmux Session 中運行，實現物理級別的預算與環境隔離。
- **WarRoom Monitoring**: 實時監控 Token 消耗、Strike 次數與心跳狀態，支援自動熔斷 (Stalled Melt)。

## Suggested State Layout

```text
.muse_state/
├── plan.json
├── diag_context_pack.json
├── diagnosis.json
├── research_pack.json
├── reflection.jsonl
├── repair_context_pack.json
├── repair_rounds.jsonl
├── repair_final.json
├── audit_context_pack.json
├── audit_result.json
├── skills_used.json
└── trace_log.jsonl
```

## Contract Evolution Rules

- JSON 是唯一權威 state 格式
- schema 演進以 append-only mental model 為主
- 新欄位應提供合理 default，避免 legacy task 讀取失敗
- 舊欄位語義不任意改名或重定義，尤其是 `repair_final` 與 `audit_result`

Recommended new state fields:

- `schema_version`
- `current_phase`
- `current_step_id`
- `steps_history`
- `external_needed`
- `external_used`
- `skills_used`
- `research_pack`
- `reflection.rounds`

## Context Hub Token Policy

### Authority Format

- `.muse_state` 與所有 phase contract 檔案一律使用 JSON
- `state_contracts.py` 只驗證 JSON schema
- TOON 不作為 state write format，也不作為跨工具交換格式

### Prompt Compression

為了降低 prompt token 成本，Context Hub 可以在「組 prompt」時，針對特定平坦陣列採用 TOON 視圖，但只限於 LLM consumption layer。

適合用 TOON 的欄位：

- `reflection.rounds` 摘要
- `research_pack.sources`
- `skills_used`
- `external_used`

Rules:

- JSON state -> 裁剪 / 摘要 -> TOON prompt view
- TOON 不寫回 `.muse_state`
- 若 agent / 環境不支援 TOON，必須 fallback 成壓縮 JSON

## Architectural Principle

核心原則不是「增加更多 agent」，而是：

> 讓每一個 phase 的輸入、輸出、責任與可回放資料都清晰。

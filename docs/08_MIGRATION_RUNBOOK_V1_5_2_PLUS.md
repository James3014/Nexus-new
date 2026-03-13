# Muse-Nexus v1.5.2+ Migration Runbook

## Purpose

這份 runbook 定義如何用「現在的 Nexus」去升級成「新版 Muse-Nexus」。

目標升級內容包含：

- Commander as workflow orchestrator
- Context Hub as context orchestrator
- skills router
- reflection memory
- external research gating
- `research_pack.json`
- step-level state

核心原則：

- 不推翻 P-D-X-R-A-C flow
- 不破壞 contract-first 思路
- 先 internal，後 external
- 舊 Nexus 先作為升級工具，不要求它一開始就完全自我重寫成功

## Treat Migration as a Single Large Muse Task

- 把「升級 Muse-Nexus 到 v1.5.2+」視為一個獨立任務
- 用新 worktree 執行，不在主 repo 混改
- 讓舊系統在隔離環境中改造自己

Suggested task id:

- `muse_upgrade_v1_5_2_plus`

## Contract Versioning Rules

當新增以下欄位時，優先採向後相容策略：

- `reflection`
- `research_pack`
- `skills_used`
- `external_used`
- `current_phase`
- `current_step_id`
- `steps_history`

Rules:

- 先 append fields，不改既有 key 語義
- `repair_final` / `audit_result` 特別不能破壞 legacy meaning
- 新欄位要有 default
- 若未完全打通，可先標 `1.5.2-rc` 或維持 `1.5.1` compatibility mode

## Recommended Upgrade Order

### Step 1. `state_contracts.py`

先擴欄位，不先做嚴格 validator：

- `schema_version`
- `current_phase`
- `current_step_id`
- `steps_history`
- `reflection`
- `research_pack`
- `skills_used`
- `external_used`

### Step 2. Repair phase

重點：

- 寫 `reflection.jsonl` 或等價 round state
- prompt 由 Context Hub 組裝
- 預留 `external_needed` hook

第一輪可接受：

- 只 log `external_needed`
- 不真的呼叫 Felo

### Step 3. Context Hub

抽離 context assembly 成正式模組。

必須能讀：

- `plan.json`
- `diagnosis.json`
- `state_diff`
- `reflection`
- `research_pack`
- `skills outputs`
- Obsidian / LanceDB memory

必須能產：

- `diag_context_pack.json`
- `repair_context_pack.json`
- `audit_context_pack.json`

### Step 4. Diag phase

加入：

- `needs_research`
- `diag_context_pack.json`

常見觸發條件：

- 第三方 API / SDK / protocol
- framework version behavior
- diagnosis 對 spec 不確定

### Step 5. Audit phase

維持既有 deterministic gates 為主幹，只預留：

- `research_pack` context slot
- code-quality slot
- prior audit failure summary slot

### Step 6. Crystal phase

先讀，不先做重決策：

- `reflection`
- `skills_used`
- `external_used`
- `research_used`

第一輪只觀察 / log 即可。

## Legacy Trace and Viz Compatibility

War Room / viz 需要接受：

- 舊任務沒有新欄位
- 新任務有 `reflection` / `skills_used` / `external_used`

Compatibility rule:

- 一律以 `.get(..., default)` 讀取
- legacy task best-effort render
- 不要求舊任務 retrofitted 到新 schema

## Self-Modification Safety Rules

### Do not let old repair loop rewrite its own core too early

初次升級時，優先：

- 讓舊 Nexus 寫候選 patch
- 人工 review / merge
- 先改外圍模組，例如：
  - `context_hub`
  - `state_contracts`
  - `reflection utils`

### Avoid half-upgraded state

危險情況：

- contract 加了欄位，但 phase / viz / router 還不支援

對策：

- 先加欄位與註解
- 一次打通一條最小完整 path
- 例如：Reflection write -> Context Hub read -> Crystal read

## External Research Integration Rules

### Phase 1: mock only

當 D / R / A 判定需要外部世界時：

- 只寫 log
- 只設 `external_needed: true`
- 不實際呼叫外部工具

### Phase 2: real routing

等 external path 穩定後，再接：

- `felo search`
- `felo web-fetch`
- 或其他 external skill

輸出統一為：

- `research_pack.json`

Fallback rule:

- 外部查詢失敗時，任務必須退回 internal-only mode

## Skills Router Rules

Skills Router 應為表驅動子模組，而不是 prompt 裡的硬編規則。

Inputs:

- `phase`
- `task_metadata`
- `language`
- `task_scale`
- `is_new_feature`
- `is_large_refactor`
- `stacktrace_pattern`

Outputs:

- skills list
- input refs
- output paths

Write-back rule:

- 所有 skill 結果統一寫入 `.muse_state` 對應 JSON / 檔案
- phase 腳本只讀 state，不直接操作 skill

## Two-Round Migration Strategy

### Round 1: Internal Learning Path

Scope:

- state contracts
- reflection
- Context Hub
- skills router skeleton
- diag / repair / audit hooks

Not included yet:

- real external calls
- Felo
- full `research_pack` production path

### Round 2: External World Path

Scope:

- `external_needed` -> external routing
- `research_pack.json`
- prompt `[SPEC / WORLD FACTS]`
- optional audit-time research

Success criteria:

- external tasks quality improves
- time / token overhead remains acceptable

## JSON and TOON Policy

### Authority state: JSON only

以下一律用 JSON：

- `.muse_state`
- `plan.json`
- `diagnosis.json`
- `repair_final.json`
- `audit_result.json`
- `trace_log.jsonl`

TOON 不可作為：

- state write format
- contract schema format
- inter-tool exchange format

### TOON as prompt-only compression

Context Hub 可以只在 prompt layer 對特定平坦 array 轉成 TOON 視圖，例如：

- `reflection.rounds`
- `research_pack.sources`
- `skills_used`
- `external_used`

Rule:

- JSON is source of truth
- TOON is prompt-only view
- agent 不支援 TOON 時，fallback to compact JSON

## Final Validation Loop

升級完成後，再開一個新的 Muse 任務，用新版 spec + 新 codebase 做一次自我審核：

- D 檢查 spec / implementation drift
- A 檢查 contract、phase、router、viz 是否一致

輸出應成為下一輪 backlog，而不是直接當作完成宣告。

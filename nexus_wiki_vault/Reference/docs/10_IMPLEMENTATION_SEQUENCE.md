---
id: 10_implementation_sequence
type: doc
status: active
created: 2026-04-07T07:29:31Z
updated: 2026-04-07T07:29:31Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/docs/10_IMPLEMENTATION_SEQUENCE.md
---
Waiver: 00_Home/[[System Overview]].md
[source: 00_Home/[[System Overview]].md]
## One-sentence summary
- Pending detailed [[documentation]].

## Role / responsibility
- Pending detailed [[documentation]].

## Upstream
- Pending detailed [[documentation]].

## Downstream
- Pending detailed [[documentation]].

## Related modules / files
- Pending detailed [[documentation]].

## Source notes
- Pending detailed [[documentation]].

## Open questions / conflicts
- Pending detailed [[documentation]].

---
# Muse-Nexus Implementation Sequence

## Purpose

這份文件把 Muse-Nexus 從「文件已定義」走到「開始落地實作」的順序排清楚。

它回答三個問題：

1. 在正式開工前，repo 還有什麼要先處理。
2. 哪些檔案應先改，哪些應延後。
3. 哪些步驟適合交給 agent，哪些步驟應人工 review。

## Pre-Implementation Check

### Current repo cleanliness

目前檢查結果：

- `git status --short` 為空
- 代表工作樹目前是乾淨的

這表示：

- 現在可以安全地開下一個 implementation branch / worktree
- 不需要先處理未提交的功能改動

### What should still be handled before code changes

雖然工作樹乾淨，但在正式實作前，仍有三件事應先明確：

1. 決定第一波只做 internal path
   - 先不上真實 Felo / external routing
   - 先做 contracts + [[Module - Intelligence and Context Core|Context Hub]] + reflection + skills router skeleton

2. 決定 canonical implementation target
   - 新架構先不要分散改很多舊腳本
   - 先選定哪些檔案是第一批落地點

3. 決定最小驗證路徑
   - 先打通一條最小 happy path
   - 不要一次同時重構 P / D / R / A / C 全部

## Recommended Execution Order

### Step 0. Freeze the baseline

Goal:

- 讓目前的文件規格成為 implementation baseline

Action:

- 以目前文件組作為唯一真相來源
- 後續變更先對照：
  - `[[02_TARGET_ARCHITECTURE]].md`
  - `[[08_MIGRATION_RUNBOOK_V1_5_2_PLUS]].md`
  - `[[09_STATE_CONTRACT_DRAFT]].md`

Human review required:

- yes

### Step 1. Define the first code landing zone

Goal:

- 決定第一批真正要落地的新模組與舊模組邊界

Recommended first landing zone:

- `state_contracts.py` 或等價 contract module
- `context_hub.py`
- `skills_router.py`
- top-level [[task]] state file strategy

Do not start with:

- `muse_viz.py`
- 真實 external routing
- 大量搬目錄

Human review required:

- yes

### Step 2. Add contract fields first

Goal:

- 先讓 state model 能容納新能力

First fields to add:

- `schema_version`
- `current_phase`
- `current_step_id`
- `steps_history`
- `external_needed`
- `skills_used`
- `external_used`
- `research_pack`
- `reflection`

Files likely touched:

- future `state_contracts.py`
- `.muse_state` file layout docs
- tests for contract [[compatibility]]

Agent suitability:

- high

Human review required:

- yes

Reason:

- schema 是所有 phase 的基礎，名稱一旦錯，後面代價會很高

### Step 3. Extract [[Module - Intelligence and Context Core|Context Hub]]

Goal:

- 把 prompt / context assembly 從現有 loop 腳本拆出去

First responsibilities:

- read `plan.json`
- read `diagnosis.json`
- read recent reflection
- read memory recall
- prepare `diag_context_pack.json`
- prepare `repair_context_pack.json`
- prepare `audit_context_pack.json`

Files likely touched:

- new `context_hub.py`
- current orchestration / repair entry script

Agent suitability:

- medium to high

Human review required:

- yes

Reason:

- 這一步決定未來 architecture 的核心邊界

### Step 4. Introduce `skills_router.py` skeleton

Goal:

- 先建立 phase -> metadata -> [[SKILL]] selection 的表驅動骨架

First version should:

- 只回傳 routing decision
- 不急著真的呼叫所有 [[SKILL]]
- 先把 output path / write-back policy 定義清楚

Minimum inputs:

- `phase`
- `language`
- `task_scale`
- `is_new_feature`
- `is_large_refactor`
- `stacktrace_pattern`

Minimum outputs:

- selected skills
- reason
- expected output target

Agent suitability:

- high

Human review required:

- yes

### Step 5. Upgrade Repair path first

Goal:

- 先把 R phase 打通，因為它最接近現有核心能力

First changes:

- reflection write
- read `repair_context_pack.json`
- record round result
- set `external_needed` without real external call

Files likely touched:

- repair engine / `codex_loop_brain.py` successor
- reflection writer
- contract write-back utilities

Agent suitability:

- medium

Human review required:

- strongly yes

Reason:

- 這一步最接近「系統改自己」

### Step 6. Upgrade Diag path

Goal:

- 讓 D phase 產生更穩定的結構化輸出

First changes:

- `diagnosis.json` contract
- `diag_context_pack.json`
- `needs_research` / `external_needed`

Agent suitability:

- medium

Human review required:

- yes

### Step 7. Upgrade Audit path

Goal:

- 保持 deterministic gates 為主，逐步接新 context

First changes:

- consume `audit_context_pack.json`
- accept `skills_used`
- accept `research_summary`
- remain backward-compatible

Agent suitability:

- medium

Human review required:

- yes

### Step 8. Add viz [[compatibility]]

Goal:

- 讓 War Room 能看懂新欄位，但不破壞舊任務

First changes:

- `.get(..., default)` safe reads
- show `external_used`
- show `skills_used`
- show reflection count

Do not do yet:

- 先不要做複雜 timeline UI

Agent suitability:

- high

Human review required:

- optional but recommended

### Step 9. Add external routing

Goal:

- 在 internal path 穩定後，才接 real X / Felo

First version should:

- route from `external_needed`
- write `research_pack.json`
- fallback to internal-only mode on failure

Agent suitability:

- medium

Human review required:

- strongly yes

Reason:

- 涉及外部依賴、失敗處理、成本控制

## What To Let Agent Do First

適合先交給 agent 的：

- contract field draft implementation
- `context_hub.py` 初版骨架
- `skills_router.py` 表驅動 skeleton
- reflection writer / reader utility
- backwards-compatible JSON read helpers

## What To Keep Under Human Review First

第一輪建議人工 review 的：

- schema naming
- file layout decisions
- ownership / canonical module decisions
- repair loop core modifications
- external routing / Felo integration

## Minimal Viable Implementation Path

如果只打一條最小可運作路徑，建議是：

```text
contracts
  -> context_hub
  -> skills_router skeleton
  -> repair path with reflection
  -> diag hook
  -> audit [[compatibility]]
```

不要一開始就做：

```text
contracts + full commander + full router + full viz + external + all phase rewrite
```

## Suggested [[task]] Breakdown

### [[task]] A. Contract Baseline

- 定義欄位
- 寫 sample JSON
- 做 legacy-safe read path

### [[task]] B. [[Module - Intelligence and Context Core|Context Hub]] Baseline

- 抽 context assembly
- 先支援 D / R / A 三個 pack

### [[task]] C. Skills Router Baseline

- 實作路由表
- 先只做 selection，不做真 [[SKILL]] execution

### [[task]] D. Repair Integration

- 接 reflection
- 接 context pack
- round write-back

### [[task]] E. Diag/Audit Integration

- 接新 packs
- 接新欄位
- 保持 backward [[compatibility]]

### [[task]] F. External Integration

- mock first
- real Felo later

## Practical Conclusion

Muse-Nexus 下一步最該做的，不是「開始改很多檔」，而是：

> 先選一條最小落地路徑，從 contract -> context -> repair 打通，再慢慢把 D / A / viz / external 接上。


---
[[System Overview]]
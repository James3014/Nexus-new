---
id: 11_first_cut_file_plan
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
path: nexus_wiki_vault/06_Ops/Reference/docs/11_FIRST_CUT_FILE_PLAN.md
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
# Muse-Nexus First-Cut File Plan

## Purpose

這份文件把第一波實作真正要碰的檔案列成清單，避免 agent 一開始就大範圍亂動。

原則：

- 只做 first-cut landing zone
- 只打通 internal path
- 先新增模組，再最小化修改現有核心腳本

## First-Cut Scope

### New files to create first

1. `scripts/core/state_contracts.py`
   - 定義最小 state model
   - 提供 sample defaults / [[compatibility]] helpers

2. `scripts/core/context_hub.py`
   - 提供 `assemble_diag_context`
   - 提供 `assemble_repair_context`
   - 提供 `assemble_audit_context`

3. `scripts/core/skills_router.py`
   - 定義 `SKILL_ROUTING`
   - 提供 `select_skills(phase, task_metadata, state)`
   - 先只回傳 routing decision，不執行 [[SKILL]]

4. `scripts/core/state_io.py`
   - 統一 `.muse_state` 路徑與 JSON/JSONL 讀寫
   - 提供 safe read / safe write / default handling

5. `scripts/core/reflection_store.py`
   - 寫入 `reflection.jsonl`
   - 讀 recent reflections

### Existing files to touch minimally

1. `scripts/codex_loop_brain.py`
   - 改為讀 `repair_context_pack`
   - 寫 reflection round
   - 寫 `external_needed`
   - 不在第一波大改主要 loop 結構

2. `scripts/drclaw_diagnosis.py`
   - 增加 `diagnosis.json` contract friendly output
   - 輸出 `needs_research`

3. `scripts/pre_write_quality_gate.py`
   - 後續再接 audit context
   - 第一波不大改，只保留相容入口

## Files Not To Touch In First Cut

- `scripts/app.py`
- `scripts/script_dashboard.py`
- `scripts/brain_search_v2.py`
- `scripts/brain_search_v3.py`
- `scripts/brain_search_v4.py`
- `scripts/flash_ingest_v2.py`
- `_migrated_from_obsidian/*`

Reason:

- 這些不是第一條 internal path 的阻塞點
- 太早動會把 migration scope 擴大

## First-Cut `.muse_state` Layout

```text
.muse_state/
├── task_state.json
├── plan.json
├── diagnosis.json
├── diag_context_pack.json
├── repair_context_pack.json
├── repair_rounds.jsonl
├── reflection.jsonl
├── audit_context_pack.json
└── trace_log.jsonl
```

第一波暫時可以不強制：

- `research_pack.json`
- `skills_used.json`
- `audit_result.json`

但要預留欄位與檔案路徑。

## Work Breakdown

### [[task]] 1. Contract layer

Files:

- `scripts/core/state_contracts.py`
- `scripts/core/state_io.py`

Expected output:

- top-level [[task]] state shape
- read/write helpers
- backward-compatible defaults

### [[task]] 2. [[Module - Intelligence and Context Core|Context Hub]] layer

Files:

- `scripts/core/context_hub.py`
- `scripts/core/reflection_store.py`

Expected output:

- context assembly [[api|API]]
- reflection read helpers

### [[task]] 3. Skills routing layer

Files:

- `scripts/core/skills_router.py`

Expected output:

- phase-based selection result
- no real [[SKILL]] execution yet

### [[task]] 4. Repair integration

Files:

- `scripts/codex_loop_brain.py`

Expected output:

- read repair context
- write reflection / state updates

### [[task]] 5. Diagnosis integration

Files:

- `scripts/drclaw_diagnosis.py`

Expected output:

- structured diagnosis output
- `needs_research` support

## Human Review Gates

這些點必須人工看過再 merge：

1. contract field names
2. `.muse_state` file naming
3. [[Module - Intelligence and Context Core|context hub]] [[api|API]] naming
4. `codex_loop_brain.py` 的核心 loop 改動
5. `needs_research` / `external_needed` semantics

## Practical Conclusion

第一波真正該動的，不是整個 repo，而是：

> `state_contracts.py` + `state_io.py` + `context_hub.py` + `skills_router.py` + 最小化修改 `codex_loop_brain.py` / `drclaw_diagnosis.py`

這樣 agent 才有清楚邊界可以施工。


---
[[System Overview]]
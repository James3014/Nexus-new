---
title: State - Schemas
aliases: [Schema Definitions, JSON Schema Hub]
type: state
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: /Users/jameschen/Workspace/schemas/
related_pages:
  - "[[Module - State Contracts]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [state, schema, contract, json]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# State - Schemas

## One-sentence summary
本頁集中說明 Nexus 系統內所有 JSON 契約的 Schema 定義位址與核心約束規則。 [Source: `schemas/`]

## Role / responsibility
- **權威索引**: 作為所有 `*_schema.json` 檔案的 Wiki 入口。 [Source: Page: Module - State Contracts]
- **結構硬化**: 強制所有 Phase Runner 產出的 .json 符合特定版本 Schema。 [Source: Spec v22 Part 4]
- **檢驗門禁**: `ci_gate.py` 在執行前會自動進行 Schema Validity 檢核。 [Source: `ci_gate.py`]

## Upstream
- **MUSE Architect**: 定義邏輯契約。
- **[[Module - State Contracts]]**: 具體化契約對位矩陣。

## Downstream
- **Phase Runners**: 執行時實體解析 Schema。 [Code: `handoff_bundle.py`]
- **[[System - Unknowns and Conflicts]]**: 登記因 Schema 更新產生的漂移。

## Related modules / files
- `/Users/jameschen/Workspace/schemas/*.json`: 實體定義文件。
- `nexus/core/handoff_bundle.py`: Schema 校驗邏輯。 [Code: `handoff_bundle.py`]

## Source notes
- Muse Engine Spec v22: 確立「所有狀態必須 Schema 化」的強制性要求。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Cross-Schema References**: 是否需要實作 `$ref` 的跨檔案解析。
- [ ] **Validation Budget**: 複雜任務下 Schema 校驗的效能損耗。

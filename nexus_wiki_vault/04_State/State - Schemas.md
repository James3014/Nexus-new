---
aliases:
- Schema Definitions
- JSON Schema Hub
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[State Contracts](../02_Modules/Module - State Contracts.md)|[[Module - [[Module - State Contracts|State
  Contracts]]|Module - [State Contracts](../02_Modules/Module - State Contracts.md)]]]]'
- '[System Overview](../00_Home/System Overview.md)'
- '[Unknowns](../01_System/System - Unknowns and Conflicts.md) and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: /Users/jameschen/Workspace/schemas/
status: active
tags:
- state
- schema
- contract
- json
title: State - Schemas
type: state
version_scope:
- v17.1
- v22
- v23
---



# State - Schemas

## One-sentence summary
本頁集中說明 Nexus 系統內所有 JSON 契約的 Schema 定義位址與核心約束規則。 [Source: 00_Home/System Overview.md]

## Role / responsibility
- **權威索引**: 作為所有 `*_schema.json` 檔案的 Wiki 入口。 [Source: 02_Modules/Module - State Contracts.md]]]
- **結構硬化**: 強制所有 Phase Runner 產出的 .json 符合特定版本 Schema。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **檢驗門禁**: `ci_gate.py` 在執行前會自動進行 Schema Validity 檢核。 [Source: ci_gate.py]

## Upstream
- **MUSE Architect**: 定義邏輯契約。
- **[Module - State Contracts](../02_Modules/Module - State Contracts.md)**: 具體化契約對位矩陣。

## Downstream
- **Phase Runners**: 執行時實體解析 Schema。 [Code: 00_Home/System Overview.md]
- **[System - Unknowns and Conflicts](../01_System/System - Unknowns and Conflicts.md)**: 登記因 Schema 更新產生的漂移。

## Related modules / files
- `/Users/jameschen/Workspace/schemas/*.json`: 實體定義文件。
- `nexus/core/handoff_bundle.py`: Schema 校驗邏輯。 [Code: 00_Home/System Overview.md]

## Source notes
- Muse Engine Spec v22: 確立「所有狀態必須 Schema 化」的強制性要求。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Cross-Schema References**: 是否需要實作 `$ref` 的跨檔案解析。
- [ ] **[[Validation|Validation]] Budget**: 複雜任務下 Schema 校驗的效能損耗。

---
[System Overview](../00_Home/System Overview.md)

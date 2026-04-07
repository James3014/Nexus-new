---
aliases:
- Runtime Flow
- Orchestration Sequence
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[State - Lifecycle](../04_State/State - Lifecycle.md)'
- '[Evidence Map](../05_Protocols/Protocol - Evidence Map.md)|[[Protocol - [[Protocol - Evidence Map|Evidence
  Map]]|Protocol - [Evidence Map](../05_Protocols/Protocol - Evidence Map.md)]]]]'
- '[System Overview](../00_Home/System Overview.md)'
- '[Unknowns](../01_System/System - Unknowns and Conflicts.md) and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags:
- flow
- runtime
- orchestration
- - - SYSTEM_ARCHITECTURE_BLUEPRINT|pxdrac
title: Flow - [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] Runtime
type: flow
version_scope:
- v22
- v23
---



# Flow - [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] Runtime

## One-sentence summary
本頁描述 Nexus 任務執行的實體調度序列，涵蓋從目標解構到經驗落盤的完整循環。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md] [Code: nexus_cli.py]

## Role / responsibility
- 本頁描述 Nexus 任務執行的實體調度序列，涵蓋從目標解構到經驗落盤的完整循環。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md] [Code: nexus_cli.py]
- **序列控制**: 確保 P -> X -> D -> R -> A -> C 相位的物理連續性。
- **工件交接**: 規範各相位產出物如何進入下一個 Phase Runner。 [Source: nexus/core/handoff_bundle.py]
- **異常處理**: 定義在任何相位失敗時的 Rollback 路徑。 [Source: scripts/engine/nexus_cli.py]

## Runtime Sequence Matrix

| Phase | Runner | Key Artifact | Source Provenance |
|---|---|---|---|
| **P** (Plan) | `nexus_plan` | `plan.json` | [Reference: plan_schema.json] |
| **X** (Explore) | `nexus_explore` | `explore_report.json` | [Source: scripts/ops/nexus_explore.py] |
| **D** (Diagnose) | `nexus_diagnose` | `diagnosis.json` | [Reference: diagnosis_schema.json] |
| **R** (Repair) | `nexus_repair` | `repair_final.json` | [Reference: repair_final_schema.json] |
| **A** (Audit) | `nexus_audit` | `audit_result.json` | [Reference: audit_result_schema.json] |
| **C** (Crystal) | `nexus_crystal` | `manifest.json` | [Reference: manifest_schema.json] |

## Upstream
- **User Intent**: 原始任務描述。
- **[State - Lifecycle](../04_State/State - Lifecycle.md)**: 提供相位權威定義。

## Downstream
- **[Protocol - Evidence Map](../05_Protocols/Protocol - Evidence Map.md)**: 追隨流程產出物理工件鏈。
- **[[Ops - CI/CD Promotion Gate]]**: 對最後產出物執行門禁檢查。

## Related modules / files
- `nexus/core/orchestrator.py`: 核心調度邏輯。 [Code: 00_Home/System Overview.md]
- `nexus/delivery/pilot_cli.py`: 命令交接引擎。 [Code: pilot_cli.py]

## Source notes
- MUSE-NEXUS Spec v22: 正式引入 Explore (X) 相位。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Parallel Execution**: 是否允許在複數任務下併發執行 D/R 相位。
- [ ] **Manual Intervention**: 在 A 相位失敗後是否允許人類手動干預並重新進入 R。

---
[System Overview](../00_Home/System Overview.md)

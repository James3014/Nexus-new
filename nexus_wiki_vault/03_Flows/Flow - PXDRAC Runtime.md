---
title: Flow - PXDRAC Runtime
aliases: [Runtime Flow, Orchestration Sequence]
type: flow
status: active
version_scope: [v22, v23]
source_of_truth: scripts/engine/nexus_cli.py
related_pages:
  - "[[State - Lifecycle]]"
  - "[[Protocol - Evidence Map]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [flow, runtime, orchestration, pxdrac]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Flow - PXDRAC Runtime

## One-sentence summary
本頁描述 Nexus 任務執行的實體調度序列，涵蓋從目標解構到經驗落盤的完整循環。 [Source: Spec v22 Part 5]

## Role / responsibility
- **序列控制**: 確保 P -> X -> D -> R -> A -> C 相位的物理連續性。
- **工件交接**: 規範各相位產出物如何進入下一個 Phase Runner。 [Source: `handoff_bundle.py`]
- **異常處理**: 定義在任何相位失敗時的 Rollback 路徑。 [Source: `nexus_cli.py`]

## Runtime Sequence Matrix

| Phase | Runner | Key Artifact | Source Provenance |
|---|---|---|---|
| **P** (Plan) | `nexus_plan` | `plan.json` | [Source: `plan_schema.json`] |
| **X** (Explore) | `nexus_explore` | `explore_report.json` | [Source: `nexus_explore.py`] |
| **D** (Diagnose) | `nexus_diagnose` | `diagnosis.json` | [Source: `diagnosis_schema.json`] |
| **R** (Repair) | `nexus_repair` | `repair_final.json` | [Source: `repair_final_schema.json`] |
| **A** (Audit) | `nexus_audit` | `audit_result.json` | [Source: `audit_result_schema.json`] |
| **C** (Crystal) | `nexus_crystal` | `manifest.json` | [Source: `manifest_schema.json`] |

## Upstream
- **User Intent**: 原始任務描述。
- **[[State - Lifecycle]]**: 提供相位權威定義。

## Downstream
- **[[Protocol - Evidence Map]]**: 追隨流程產出物理工件鏈。
- **[[Ops - CI/CD Promotion Gate]]**: 對最後產出物執行門禁檢查。

## Related modules / files
- `nexus/core/orchestrator.py`: 核心調度邏輯。 [Code: `orchestrator.py`]
- `nexus/delivery/pilot_cli.py`: 命令交接引擎。 [Code: `pilot_cli.py`]

## Source notes
- MUSE-NEXUS Spec v22: 正式引入 Explore (X) 相位。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Parallel Execution**: 是否允許在複數任務下併發執行 D/R 相位。
- [ ] **Manual Intervention**: 在 A 相位失敗後是否允許人類手動干預並重新進入 R。

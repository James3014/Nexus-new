---
title: Module - State Contracts
aliases: [State Contracts, JSON Schemas]
type: module
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: /Users/jameschen/Workspace/schemas/
raw_sources: [plan_schema.json, diagnosis_schema.json, repair_final_schema.json, audit_result_schema.json, manifest_schema.json]
related_pages:
  - "[[State - Lifecycle]]"
  - "[[State - Schemas]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [module, state, contracts, json-schema]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Module - State Contracts

## One-sentence summary
本頁定義 Nexus 任務執行過程中必須遵循的 5 大 JSON 狀態契約與跨檔案不變量。 [Reference: Spec v22]

## Role / responsibility
- **結構校驗**: 確保所有任務工件符合 `plan`, `diagnosis`, `repair`, `audit`, `manifest` 結構。 [Reference: manifest_schema.json]
- **不變量維護**: 強制要求 `task_id` 與 `trace_id` 在整個 Evidence Chain 中保持一致。 [Reference: Spec v22 Part 4.1]
- **風險分級**: 根據 `audit_result.json` 的 `risk_score` 決定門禁通過與否。 [Source: scripts/ops/ci_gate.py]

## Core Contracts Matrix

| Contract | Purpose | Key ID | Source Provenance |
|---|---|---|---|
| `plan.json` | 任務目標與 TODO | `task_id` | [Reference: plan_schema.json] |
| `diagnosis.json` | 現狀診斷與 Trace | `trace_id` | [Reference: diagnosis_schema.json] |
| `repair_final.json`| 修復方案與 Patch | `patch_hash` | [Reference: repair_final_schema.json] |
| `audit_result.json`| 審計風險評估 | `risk_score` | [Reference: audit_result_schema.json] |
| `manifest.json` | 最終證據封裝 | `seal_status` | [Reference: manifest_schema.json] |

## Upstream
- **Phase Runners**: 產出符合這些 Schema 的實體 JSON。 [Source: scripts/engine/nexus_cli.py]
- **Core Orchestrator**: 根據契約內容進行相位調度。 [Source: nexus/core/orchestrator.py]
- `nexus/core/handoff_bundle.py`: 狀態交接封裝邏輯。 [Source: nexus/core/handoff_bundle.py]
- v22 Engine Spec: 確立 `manifest.json` 為唯一權威索引。 [Reference: Spec v22]

## Downstream
- **[[System - Unknowns and Conflicts]]**: 登記 Schema 漂移衝突。
- **[[Ops - CI/CD Promotion Gate]]**: 基於契約數值執行發佈決策。

## Related modules / files
- `/Users/jameschen/Workspace/schemas/`: 實體 JSON Schema 定義。
- `nexus/core/handoff_bundle.py`: 狀態交接封裝邏輯。 [Code: `handoff_bundle.py`]

## Source notes
- Hardened v17.1 Spec: 建立最初的 4 相位工件對位要求。
- v22 Engine Spec: 確立 `manifest.json` 為唯一權威索引。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Contract Versioning**: 預留 `contract_version` 欄位以支援跨版本的 Schema 兼容性。
- [ ] **Schema Evolution**: v23 智慧層是否應具備動態調整 Audit 閾值的能力。

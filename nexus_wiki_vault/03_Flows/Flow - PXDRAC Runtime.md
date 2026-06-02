---
aliases:
- Runtime Flow
- Orchestration Sequence
confidence: high
last_compiled: 2026-06-02
owner: agent
related_pages:
- '[State - Lifecycle](../04_State/State - Lifecycle.md)'
- '[Evidence Map](../05_Protocols/Protocol - Evidence Map.md)'
- '[System Overview](../00_Home/System Overview.md)'
source_of_truth: src/governance/transition_engine.rs
status: active
tags:
- flow
- runtime
- orchestration
- rust
- hybrid
title: Flow - PXDRAC Runtime (Hybrid v24.0)
type: flow
version_scope:
- v24.0
- v26
---

# Flow - PXDRAC Runtime (Hybrid v24.0)

## One-sentence summary
本頁描述 Nexus v24.0 的實體調度序列，所有相位轉移均由 Rust Kernel 進行物理級裁決與 Fail-Closed 保障。 [Source: src/governance/transition_engine.rs]

## Role / responsibility
- **物理連續性 (Physical Continuity)**: 由 Rust `TransitionEngine` 確保 P -> X -> D -> R -> A -> C 相位的絕對順序，禁止任何未經授權的跳步。
- **標籤導向調度 (Tag-Driven Orchestration)**: 模型僅提供語義標籤 (r:x, d:x, p:x)，不控制最終的 JSON 結構。
- **自動化 Receipt 補全**: 當 Rust Kernel 許可轉移後，由 Python 層依據 `TypedContract` 自動補全標準治理證據。

## Hybrid Runtime Sequence Matrix

| Phase | Semantic Target | Hard Enforcement (Rust) | Key Artifact (Typed Receipt) |
|---|---|---|---|
| **P** (Plan) | `p:1` | `TransitionGuard(INTAKE -> PLAN)` | `plan_receipt.v2` |
| **X** (Explore) | `p:x` | `ContaminationGuard` | `explore_receipt.v2` |
| **D** (Diagnose) | `p:3` | `TransitionGuard(PLAN -> EXECUTE)` | `diagnosis_receipt.v2` |
| **R** (Repair) | `p:3` | `TypedContract(EXECUTE)` | `repair_receipt.v2` |
| **A** (Audit) | `p:4` | `ReceiptVerifier(VERIFY)` | `audit_receipt.v2` |
| **C** (Crystal) | `p:6` | `TransitionGuard(VERIFY -> CLOSE)` | `closure_receipt.v2` |

## Upstream
- **Semantic Adapter**: 提供 7B/14B 的意圖判定標籤。
- **[State - Lifecycle](../04_State/State - Lifecycle.md)**: 提供相位的 SSOT 定義。

## Downstream
- **Rust Governance Kernel**: 執行最終的物理攔截與裁決。
- **[Protocol - Evidence Map](../05_Protocols/Protocol - Evidence Map.md)**: 儲存經 Rust 驗證後的物理工件鏈。

## Related modules / files
- `src/governance/transition_engine.rs`: 核心轉移引擎。
- `nexus/engine/semantic_adapter.py`: 語義標籤適配器。
- `nexus/engine/governance_bridge.py`: Python ↔ Rust 橋接層。

## Source notes
- v24.0 Pivot: 徹底廢棄了模型直出完整治理 JSON 的模式，改為「語義標籤 + 物理狀態機」的 Hybrid 模式。 [Source: docs/perplexity/RELEASE_NOTE_v2.3.md]


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


---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]

---
aliases:
- State Contracts
- JSON Schemas
- Pydantic Enforced
confidence: high
last_compiled: '2026-05-17'
owner: agent
raw_sources:
- nexus/engine/completion_contract.py
- nexus/engine/capability_contracts.py
- nexus/engine/phases/base.py
related_pages:
- '[[04_State/State - Lifecycle.md]]'
- '[[04_State/State - Schemas.md]]'
- '[[00_Home/System Overview.md]]'
source_of_truth: nexus/engine/completion_contract.py
status: active
tags:
- module
- state
- contracts
- pydantic
title: Module - State Contracts
type: module
version_scope:
- v26
---

# Module - State Contracts (v26 Pydantic Enforced)

## One-sentence summary
本頁定義 Nexus v26 的狀態契約，全面採用 Pydantic 硬化驗證，確保任務工件在 P-X-D-R-A-C 閉環中的結構一致性與證據完整性。 [Source: nexus/engine/completion_contract.py]

## Role / responsibility
- **強型別校驗**: 透過 Pydantic 模型強制執行 `Task`, `ExecutionPlan`, `NexusReceipt` 的欄位規範。
- **不變量維護**: 物理保證 `task_name` 與 `execution_path` 在整個 Evidence Chain 中不可篡改。
- **證據封裝**: 透過 `build_completion_envelope` 產出具備語義標籤 (Semantic Status) 的最終工件。

## Core Contracts Matrix (v26)

| Contract | Purpose | Data Model | Source Provenance |
|---|---|---|---|
| **Completion Envelope** | 任務最終狀態與證據封裝 | `dict (Future: Pydantic)` | [Source: nexus/engine/completion_contract.py] |
| **Capability Plan** | 路由選定的能力與待執行項目 | `CapabilityPlan` | [Source: nexus/engine/capability_contracts.py] |
| **Capability Receipt** | 執行證據與 Gate 驗證結果 | `CapabilityReceipt` | [Source: nexus/engine/capability_contracts.py] |
| **Skill Receipt** | 特定技能調用的原子證據 | `SkillReceipt` | [Source: nexus/engine/capability_contracts.py] |
| **Nexus State** | 核心運行時狀態機 | `NexusState` | [Source: nexus/core/state_contracts.py] |

## Upstream
- **Phase Runners**: 產出符合模型定義的實體數據。 [Source: nexus/engine/phases/base.py]
- **Capability Router**: 根據路由結果生成 `CapabilityPlan`。 [Source: nexus/engine/autonomic_router.py]

## Downstream
- **[[04_State/State - Schemas|State - Schemas]]**: 定義狀態枚舉與轉移規則。
- **[[Ops - CI/CD Promotion Gate]]**: 基於契約數值執行發佈決策。

## Related modules / files
- `nexus/engine/completion_contract.py`: 任務完成封裝邏輯。
- `nexus/engine/capability_contracts.py`: 能力與收據模型定義。
- `nexus/core/state_contracts.py`: 核心狀態機。

## Source notes
- v26 Pydantic Enforced: 廢棄舊版 `json-schema` 物理檔案校驗，全面轉向代碼內置的 Pydantic 模型驗證，提升開發效率與運行時安全性。 [Source: nexus/engine/completion_contract.py]

## Open questions / conflicts
- [ ] **Protobuf Integration**: 評估是否將高性能路徑 (High-path) 的狀態交換轉換為 Protobuf 以支援 Swarm 大規模通訊。

---
[System Overview](../00_Home/System Overview.md)
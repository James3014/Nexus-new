---
aliases: '[Router Flow, Strategy Routing, Memory Routing]'
confidence: high
last_compiled: '2026-05-17'
owner: agent
source_of_truth: nexus/engine/autonomic_router.py
status: hardened
tags: '[core, architecture, router, flow]'
title: Module - Router Decision Flow
---

# Module - Router Decision Flow (v26 Hardened)

## One-sentence summary
本頁解析 `AutonomicRouter` (v4.40) 的決策邏輯，描述其如何結合預審、Harness 策略與證據收據 (Receipts) 驅動路由決定。 [Source: nexus/engine/autonomic_router.py]

## Role / responsibility
- 定義路由決策流程與保護性檢查順序，確保每個任務都有可回放的流程邏輯。 [Source: nexus/engine/autonomic_router.py]
- 對上游 Orchestrator 提供模式切換與結果標註，支持 `NexusReceipt` 的證據鏈生成。 [Source: nexus/engine/capability_receipts.py]

## Upstream
- `nexus/core/orchestrator.py`: 提供主循環節點與異常回退策略。 [Source: nexus/core/orchestrator.py]
- `nexus/engine/harness_route_policy.py`: 提供能力降級 (Downgrade) 與治理保護 (Protection) 指引。 [Source: nexus/engine/harness_route_policy.py]

## Downstream
- `Module - Core Orchestrator`: 使用本決策結果推進任務執行。 [Source: 02_Modules/Module - Core Orchestrator.md]
- `Capability Receipt Adapter`: 根據路由結果與執行證據產出驗證收據。 [Source: nexus/engine/capability_receipt_adapters.py]

## Related modules / files
- `nexus/engine/autonomic_router.py`: 路由核心實作。
- `nexus/engine/harness_route_policy.py`: 治理與成本策略。
- `nexus/engine/capability_receipts.py`: 證據收據生成邏輯。

## Source notes
- v26 Hardening: 引入 `all_positive_pass = True` 的硬門檻，並將路由邏輯移至 `nexus/engine`。 [Source: nexus/engine/autonomic_router.py]

## Open questions / conflicts
- [x] **Policy Conflict**: 已透過 `harness_route_policy.py` 解決。特定 diagnostic/oracle 合約必須覆蓋成本懲罰。 [Source: ADR-2026-05-08-route-oracle-receipt-contract.md]

## ⚙️ 決策流程 (The Routing Process)

### Step 1: 倫理與美學預審 (Critique Prescan)
- 調用 `CritiqueEngine` 掃描查詢語句，阻斷「反合理化」行為。

### Step 2: 任務特徵提取 (Stemming & Expansion)
- 使用 `AutonomicRouter` 對任務描述進行 `_stem` 處理（如 `fix` -> `fix`, `security` -> `secu`）。
- 透過 `EXPANSIONS` 矩陣擴展語義（如「權限」-> `perm`）。

### Step 3: Harness 策略過濾 (Harness Route Policy)
- 調用 `derive_impact_tags` 鑑定任務影響。
- 根據 `harness_route_policy.py` 判定是否需降級高成本能力（如 `ultra_review`）或保護核心治理組件（如 `artifact_gate`）。

### Step 4: 雙模檢索 (Dual-Mode Search)
- **Palace Search (Tier 0)**: 優先搜尋 `memory_index.lancedb` 中的硬性規約。
- **Policy Memory (Tier 1)**: 讀取 `policy_memory.jsonl`，結合 `v4_hardened` 標記過濾不適用的政策。

### Step 5: 證據路徑預定 (Receipt Slotting)
- 根據選定的能力，在 `capability_receipts.py` 中預留證據插槽，確保執行後能產出 `CapabilityReceipt`。

## 🛡️ 實體合約 (Input/Output Contract)
- **Input**: `task_desc`, `state (NexusState)`, `forecast`, `pre_routing`.
- **Output**: `ExecutionPlan` (包含 `mode`, `reason`, `confidence`, `matched_policies`).

---
**[Source: nexus/engine/autonomic_router.py]**

[[System Overview]]

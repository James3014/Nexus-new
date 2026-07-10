---
id: ADR-2026-07-08-no-duplicate-wheel-guard
date: 2026-07-08
title: 6 條重複造輪子防呆原則 — Phase 8 規劃永久規範
status: accepted
confidence: high
related_pages:
- '[[../09_Roadmap/Phase 8 - Hybrid Repair Armor]]'
- '[[ADR-2026-07-08-capability-planner-downstream-enforcement]]'
- '[[ADR-2026-07-08-paw-compiler-seam-fuzzy-bug]]'
- '[[../../06_Ops/Ops - Learning Closure Matrix]]'
source_of_truth: nexus/contracts/, nexus/services/local_heal/, nexus/engine/
tags:
- adr
- phase8
- anti-pattern
- no-duplicate-wheel
- grepp-first
- downstream-first
---

# ADR-2026-07-08：6 條重複造輪子防呆原則（永久規範）

## Status
Accepted — 2026-07-08

## Context

Phase 8（Hybrid Repair Armor）規劃時實機稽核發現：
- 7 個規劃新 module 中，**4 個與既有重疊**（PAW compiler seam、Claim Gate quota 依賴、Cascade controller、Knowledge Agent 索引）
- 既有 module 已完整實作：`fuzzy_spec_registry.py` / `claim_delivery_gate.py` / `p3_local_retry_stub.py` / `autonomic_router.py` / `completion_contract.py` 等
- 若不規範，未來 agent 會繼續重複造輪子，破壞既有契約

從 `Nexus本地委員會全能力路由接軌查證報告_20260706.md` 與 `nexus_downstream_enforcement_plan (1).md` 得知 Nexus 已 1143 tests passed，**任何新 module 都不可破壞既有測試**。

## Decision

永久採用 6 條「重複造輪子防呆原則」：

### 原則 1：grep 先決
任何新建 module 前，必須跑 `find ... -name '*.py' | xargs grep -l '<關鍵字>'` 至少 2 次：
- 概念詞（AUTOMEM / SHEPHERD / PAW / semantic_correctness / quota_monitor）
- 既有 module 名（cascade_orchestrator / claim_gate / autonomic_router / completion_contract）
- 既有 contract 詞（HybridRouteDecision / CanonicalPatchCandidate / QuotaState / DegradationDecision）

若 grep 命中 ≥ 1，**不可新建**，必須改寫既有或拒絕規劃。

### 原則 2：既有 fuzzy / completion / claim / router 優先
下列 4 個 module 已有完整實作，**只能補不能新建**：
- `nexus/services/local_heal/fuzzy_spec_registry.py`（PAW 雛形已備）
- `nexus/services/local_heal/completion_contract.py`（semantic_status 已有）
- `nexus/services/local_heal/claim_delivery_gate.py`（public_claim_allowed 強制已有）
- `nexus/engine/autonomic_router.py`（v4.40 MVP Hardened，不能碰）

### 原則 3：shadow-only 翻成 runtime 必走雙胞胎
既有 `p3_*_shadow_only` family（C15/C6 全部 contract）**不可**覆寫。新 runtime **必須**寫為 `p3_*_runtime_enabled` 雙胞胎，與 shadow 平行。runtime_enabled **不**影響 shadow_only 行為。

### 原則 4：CapabilityPlanner 下游不碰
任何「route / topology / model selection」程式碼都**不可**新增。包括：
- 新 `RouteMode` enum 值
- 新 `Router` 類別
- 新 `Planner` 類別
- 新 `topology_selector` 邏輯
- 新 `execution_topology` 解析（在 `LocalModelExecutor` 內自選）

`execution_topology` 只能由 `signal_snapshot` 注入，不可由 `LocalModelExecutor` 自選（見 `local_model_executor.py:_resolve_execution_topology` 邊界）。

### 原則 5：概念詞 grep 必須 0 命中才可新建
Phase 8 新建 module 的概念詞 grep 結果：
- `AUTOMEM` / `autonomous_memory` / `memory_curator`：0 命中 → ✅ P4-2 可新建
- `SHEPHERD` / `shepherd_supervisor`：0 命中 → ✅ P4-3 可新建
- `PAW` / `paw_compiler_seam`：命中 `fuzzy_spec_registry.py` / `fuzzy_functions.py` → ❌ P4-4 **不可新建**（改寫既有）
- `semantic_correctness` / `post_state_hash` / `assertion_grounded`：0 命中 → ✅ P0 可新建
- `quota_monitor` / `QuotaMonitor` / `quota_watcher`：0 命中 → ✅ P3-1 可新建
- `DegradationController` / `runtime_degradation`：0 命中 → ✅ P3-2 可新建
- `EvoEmbedding` / `evo_embedding`：0 命中 → ✅ P4-1 可新建
- `cascade` / `Cascade`：命中 8 個 → ⚠️ P2 先 audit 再補，不新建
- `claim_delivery_gate` / `public_claim_allowed.*quota`：命中既有 → ⚠️ P3-2 改寫不新建

### 原則 6：v28 architecture freeze 4 模組邊界不可破
`28_V28_ARCHITECTURE_FREEZE.md` 凍結 4 個核心模組公共介面：
- `nexus.state.task_state_store`（狀態 SSoT）
- `nexus.telemetry.telemetry_models`（遙測）
- `nexus.memory.memory_retrieval_service`（檢索）
- `nexus.gate.gate_judge`（判決器）

任何新 module 不可改這 4 個模組的公共介面。**只能呼叫**，不可繼承覆寫。

## Consequences

### Positive
- 7 個規劃新 module 中 4 個去重 → 最終 6 個真實新建
- 12 個既有 module 改寫而非新建，**不破壞** 1143 tests
- 14 個 override points 不再增加（從既有 `nexus_downstream_enforcement_plan` 維持）
- 12 條不可變規則 + 6 條重複造輪子防呆原則全部沿用既有 Learning Closure Matrix
- `autonomic_router.py` / `claim_delivery_gate.py` / `fuzzy_spec_registry.py` 等關鍵模組不重複

### Negative
- grep 流程需在每個新 P 啟動前跑（增加 ~10 分鐘前置時間）
- 改寫既有 module 需小心維持向後相容（既有測試不可破）

### Neutral
- 本 ADR 與 `ADR-2026-07-08-paw-compiler-seam-fuzzy-bug.md` 的 PAW 改寫決策完全相容
- 本 ADR 與 `ADR-2026-07-08-capability-planner-downstream-enforcement.md` 的 7 條邊界完全相容
- 既有 `Ops - Learning Closure Matrix.md` 的所有 reason code 仍適用

## Verification

每個新 P 啟動前必跑：
```bash
# 原則 1：grep 先決
find /Users/jameschen/Workspace/nexus/nexus -name '*.py' | xargs grep -l '<新模組關鍵字>' 2>/dev/null
# 預期：0 命中

# 原則 2：既有優先 module 不可動
ls -la /Users/jameschen/Workspace/nexus/nexus/services/local_heal/fuzzy_spec_registry.py
ls -la /Users/jameschen/Workspace/nexus/nexus/services/local_heal/completion_contract.py
ls -la /Users/jameschen/Workspace/nexus/nexus/services/local_heal/claim_delivery_gate.py
ls -la /Users/jameschen/Workspace/nexus/nexus/engine/autonomic_router.py

# 原則 3：shadow-only 不覆寫
find /Users/jameschen/Workspace/nexus/nexus/services/local_heal -name 'p3_*_shadow_only.py'

# 原則 4：route authority 不下放
grep -r 'route_truth_source' /Users/jameschen/Workspace/nexus/nexus/contracts/hybrid_route.py

# 原則 5：概念詞 0 命中
find /Users/jameschen/Workspace/nexus/nexus -name '*.py' | xargs grep -l '<新概念詞>' 2>/dev/null

# 原則 6：v28 freeze 4 模組不破
diff docs/governance/v28.2_REGRESSION_BASELINE.md <(git show HEAD:docs/governance/v28.2_REGRESSION_BASELINE.md)
```

## References

- [Phase 8 - Hybrid Repair Armor](../09_Roadmap/Phase%208%20-%20Hybrid%20Repair%20Armor.md)
- [ADR-2026-07-08-capability-planner-downstream-enforcement](ADR-2026-07-08-capability-planner-downstream-enforcement.md)
- [ADR-2026-07-08-paw-compiler-seam-fuzzy-bug](ADR-2026-07-08-paw-compiler-seam-fuzzy-bug.md)
- [Ops - Learning Closure Matrix](../../06_Ops/Ops%20-%20Learning%20Closure%20Matrix.md)
- `MUSE_PROTO.md`（agent 必讀）
- `28_V28_ARCHITECTURE_FREEZE.md`（4 模組凍結）
- `nexus_downstream_enforcement_plan (1).md`（2026-07-07，14 override points 現況）
- `nexus_route分裂查證報告_2026-06-30 (1).md`（ROUTE_SPLIT: not observed）
- `Nexus_Knowledge_Agent_Integration_v2 (1).md`（Knowledge Agent audit layer 邊界）
- `Nexus本地委員會全能力路由接軌查證報告_20260706.md`（1143 tests passed）
- `Downloads/NEXUS_HYBRID_REPAIR_CORRECTION_20260708.md`（完整稽核版本）

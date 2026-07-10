---
id: ADR-2026-07-08-capability-planner-downstream-enforcement
date: 2026-07-08
title: Phase 8 Hybrid Repair Armor — CapabilityPlanner Downstream Enforcement 邊界
status: accepted
confidence: high
related_pages:
- '[[../09_Roadmap/Phase 8 - Hybrid Repair Armor]]'
- '[[../../06_Ops/Ops - Learning Closure Matrix]]'
- '[[../../09_Roadmap/Phase 6 - Nexus Hardening]]'
source_of_truth: nexus/contracts/hybrid_route.py, nexus/engine/capability_planner.py
tags:
- adr
- phase8
- boundary
- capability-planner
- downstream-enforcement
- hybrid-repair
---

# ADR-2026-07-08：Phase 8 Hybrid Repair Armor 的 CapabilityPlanner Downstream Enforcement 邊界

## Status
Accepted — 2026-07-08

## Context

Phase 8（Hybrid Repair Armor）要把 Nexus 從「零件齊全」升級為「雙模式修復系統」（Mode A：Cloud + Local Assist / Mode B：Local Only），需要新建 6 個 module、改寫 12 個 module。但從 `nexus_downstream_enforcement_plan`（2026-07-07 報告）得知：

- CapabilityPlanner / HybridRouteDecision 是**唯一** route authority
- LocalModelExecutor / CommitteeOrchestrator / RuntimePolicy 是 pure downstream consumer
- 已清除 29 個 override points（43→14）
- C6AX D/A committee live-verified 但仍遵守 downstream consumer 邊界
- 任何「route / topology / model selection」程式碼都**不可**新增

新規劃若不嚴守此邊界，會重蹈「`capability_adapter` 24 個 legacy RouteMode」的覆轍（已在 quarantine 完成）。

## Decision

Phase 8 全部 6 個 P（P0-P5）必須遵守以下 7 條邊界契約：

### 邊界 1：route authority 不可下放
- `route_truth_source` 永遠是 `CapabilityPlanner`
- `HybridRouteDecision` 8 種 `RouteMode` 不可新增
- `execution_topology` 由 `signal_snapshot` 注入，不可在 `LocalModelExecutor` 內自選

### 邊界 2：Knowledge Agent = audit/retrieval/evidence support layer
- `KnowledgeHitSignal` 可 enrich `SignalSnapshot` 作為 downstream signal
- **不可**自動選擇 route / topology / model
- **不可**改 parser / verifier / candidate isolation

### 邊界 3：shadow-only 翻 runtime 必走雙胞胎
- 保留 `p3_*_shadow_only` family（既有 C15/C6 全部 contract）
- 新寫 `p3_*_runtime_enabled` family（與 shadow 平行）
- runtime_enabled **不**覆寫 shadow_only 行為

### 邊界 4：PAW / SHEPHERD / AUTOMEM 只能補既有
- PAW 不新建 `paw_compiler_seam.py`，改寫 `fuzzy_spec_registry.py`（已有 5 個 fuzzy function 帶 `paw_backend_available` 欄位）
- SHEPHERD 新建 `shepherd_supervisor.py` 但只能「分叉 / 觀察 / 改 sub-agent 定義」
- AUTOMEM 新建 `autonomous_memory_curator.py` 但只改 Harness（提示詞 / 檔案格式 / 動作詞彙），不動主模型

### 邊界 5：CapabilityPlanner 下游不碰
- `autonomic_router.py`（v4.40 MVP Hardened）**不能碰**
- `SkillsRouter.route_candidates()`（`router.py:269-334`）**不能碰**
- 任何「route / topology / model selection」程式碼**不可**新增

### 邊界 6：claim gate 預設全 false
- `public_claim_allowed=False`
- `production_ready=False`
- `internal_only=True`
- `local_only_executed` 模式 → 強制 `public_claim_allowed=False`

### 邊界 7：v28 architecture freeze 4 模組邊界
- `nexus.state.task_state_store`（狀態 SSoT）
- `nexus.telemetry.telemetry_models`（遙測）
- `nexus.memory.memory_retrieval_service`（檢索）
- `nexus.gate.gate_judge`（判決器）
- 4 個模組的公共介面**不可**改

## Consequences

### Positive
- 6 個新 module 全部在既有 contract 邊界內
- 12 個改寫模組的補丁**不破壞**既有的 1143 tests（local_heal 套件）
- CapabilityPlanner 仍是唯一 route authority，下游 14 個 override points 不再增加
- 12 條不可變規則 + 6 條重複造輪子防呆原則全部沿用既有 Learning Closure Matrix

### Negative
- Mode A 真實 cloud 呼叫需要 `NEXUS_CLOUD_API_KEY` env（目前 env-guarded）
- Quota Monitor 觀察 cloud 需要 provider API 支援（部分 provider 沒公開 quota API）
- SHEPHERD supervisor 對 sub-agent 改定義需 sub-agent 支援 structured event trace（目前部分 worker 沒完整實作）

### Neutral
- 本 ADR 與既有 `ADR-2026-05-14-nexus-wearing-gate-stabilization.md` 邊界完全相容
- 本 ADR 與既有 `ADR-2026-05-07-route-ab-infra-invalid-lesson.md` 教訓對齊

## Verification

每個 P 結束時必跑：
- `tests/contracts/test_hard_gate_compatibility.py`（public_claim_allowed / production_ready 0 violation）
- `tests/benchmark/test_h7_route_receipt_schema_consistency.py`（route_truth_source 100% CapabilityPlanner）
- `tests/services/local_heal/test_output_understanding.py`（hash chain 100%）
- `tests/contracts/test_failure_taxonomy_coverage.py`（reason code 100%）
- `docs/governance/v28.2_REGRESSION_BASELINE.md` diff（0 diff）
- `scripts/ops/ci_gate.py --full-dry-run`（PASS）
- `tests/benchmark/test_full_capability_matrix.py`（本地 + Online 兩模式各 25/25 能力可用，新建）

## References

- [Phase 8 - Hybrid Repair Armor](../09_Roadmap/Phase%208%20-%20Hybrid%20Repair%20Armor.md)
- [Phase 6 - Nexus Hardening](../09_Roadmap/Phase%206%20-%20Nexus%20Hardening.md)
- [Ops - Learning Closure Matrix](../../06_Ops/Ops%20-%20Learning%20Closure%20Matrix.md)
- `MUSE_PROTO.md`
- `28_V28_ARCHITECTURE_FREEZE.md`
- `nexus/contracts/hybrid_route.py`（HYBRID_ROUTE_DECISION_SCHEMA = "nexus.hybrid_route_decision.v1"）
- `nexus/engine/capability_planner.py:898`（proposer_specs / judge_model / delegated_retry_candidate_models 注入 signal_snapshot）
- `nexus_downstream_enforcement_plan (1).md`（2026-07-07）
- `nexus_route分裂查證報告_2026-06-30 (1).md`（ROUTE_SPLIT: not observed）
- `Nexus_Knowledge_Agent_Integration_v2 (1).md`（Knowledge Agent 邊界）

---

---

## 邊界 8（P30）已遷移至主規劃報告

本 ADR 原含邊界 8（P30 AutonomicRouter 降級條款），於 2026-07-08 v3 改版時**遷移**至 `Downloads/NEXUS_HYBRID_REPAIR_REPORT_20260708.md` 作為「未來執行規劃起頭」。

**理由**：邊界 8 是「如何降級 AutonomicRouter」的實作條款，與 ADR 其他 7 條「CapabilityPlanner 不能下放」邊界性質不同。實作條款適合放在主規劃報告（執行起頭），契約邊界適合留在 ADR（永久規範）。

**完整 P30 內容請參考**：`Downloads/NEXUS_HYBRID_REPAIR_REPORT_20260708.md` §0.5「P30 AutonomicRouter 降級條款」。

**ADR 邊界仍包含 7 條**：邊界 1-7 不變，與 P30 無重疊。

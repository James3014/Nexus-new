# Policy Baseline Manifest v1 — 說明文件

**版本**：v1.0.0
**生成時間**：2026-06-15
**Commit SHA**：`1c9dce6597f3eb52006df8223000d2162624f55d`
**原則**：baseline freeze, not expansion

---

## 概述

本 manifest 凍結 Nexus 當前所有治理政策的 baseline，作為後續所有變更的 reference point。

---

## Status Tag 定義

| Tag | 意義 | 可否作為 sealed evidence |
|-----|------|--------------------------|
| `code-backed` | 規則有對應的 production code，可被直接執行 | ✅ 可以 |
| `spec-backed` | 規則有 spec 或 design doc，但 code 可能不完整 | ⚠️ 有限 |
| `inferred` | 從 code 行為推斷，但無明確定義 | ❌ 不可以 |
| `historical` | 曾存在但已不活躍，或僅在特定 commit 存在 | ❌ 不可以 |

---

## Governance Chain Coverage

### Research Isolation
- **Modules**: `nexus/research/`, `nexus-core-rs/src/contamination.rs`
- **Receipts**: `ContaminationCheckResult`
- **Status**: `partial` — contamination guard 存在但 keyword list 硬編碼

### Route Decision
- **Modules**: `nexus/engine/autonomic_router.py`, `nexus/services/s2t_strict.py`
- **Receipts**: `ExecutionPlan`, `S2TStrictDecision`
- **Status**: `complete` — routing 有完整 code path + receipt

### Pre-Patch
- **Modules**: `nexus/services/local_heal/`, `nexus/engine/patch/`
- **Receipts**: `PatchInputClassifier`, `patch_invocation_boundary_receipt`
- **Status**: `inferred` — patch boundary 邏輯散在多個 module，無統一 receipt schema

### Autonomy / Verification / Closeout
- **Modules**: `nexus/engine/autonomy_observation.py`, `nexus/services/local_heal/evaluation_gate.py`, `nexus/engine/attempt_settlement_service.py`
- **Receipts**: `AutonomyObservationReceipt`, `TestResult`, `AutoEvidence`
- **Status**: `complete` — 有完整 code path + receipt

### Claimability
- **Modules**: `nexus/core/critique_engine.py`, `nexus/governance/hallucination_guard.py`, `nexus/engine/capability_receipt_policy.py`
- **Receipts**: `HallucinationNote`, `HallucinationAnalysis`, `CoverageReport`
- **Status**: `complete` — 有 schema-driven scoring + policy check

---

## Rollback Drill Status

**所有 27 條 policy 的 rollback drill status 均為 `drilled-2026-06-15`。**

這表示：
- 所有 policy 皆已在 [policy-rollback-drill-matrix.md](file://./policy-rollback-drill-matrix.md) 中完成明確定義的 rollback path 與驗證方式。
- 全部 policy 皆已通過 rollback 測試的完整校準，符合運行時高可用性退避 (Fallback) 與回滾要求。

---

## Promotion Allowed

**所有 27 條 policy 的 promotion_allowed 均已變更為 `true`。**

在 rollback drill 演練定義全量通過的條件下，所有 baseline policy 均已被授予 promotion 資格，可以進入後續階段的 integration 或者是 higher confidence level promotion。

---

## Rust Kernel Policies

以下 3 條 policy 位於 Rust kernel，目前已完成 `code-backed` 硬化：

| Policy ID | Module | Schema Version | Status | Rollback Status |
|-----------|--------|----------------|--------|-----------------|
| P-GATE-03 | receipt_verifier | v1.0 | code-backed | drilled-2026-06-15 |
| P-FLOW-01 | flow_machine | v1.0 | code-backed | drilled-2026-06-15 |
| P-CONTAM-01 | contamination_guard | v0.1 | code-backed | drilled-2026-06-15 |

**驗證狀態**：Rust kernel 的 unit tests 目前共有 **38 條**，已全數通過 (`cargo test` 全綠)。
此外，已透過 `test_rust_kernel_smoke.py` 與 `test_rust_wave3_cutover.py` 的雙軌測試 (dual-run mismatch = 0) 完成驗證。

---

## 使用方式

1. **變更追蹤**：任何 policy 變更必須更新此 manifest 的 commit_sha 和 schema_version
2. **Rollback 參考**：rollback 時對照此 manifest 與 [policy-rollback-drill-matrix.md](file://./policy-rollback-drill-matrix.md) 確認 policy 狀態
3. **Promotion Gate**：所有 policy 均已完成 rollback drill，允許進一步推廣與部署。

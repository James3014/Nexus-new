# Policy Baseline Manifest v1 — 說明文件

**版本**：v1.0.0
**生成時間**：2026-06-15
**Commit SHA**：`1c9dce6597f3eb52006df8223000d2162624f55d`
**原則**：baseline freeze, not expansion

---

## 概述

本 manifest 凍結 Nexus 當前所有治理政策的 baseline，作為後續所有變更的 reference point。

**重要**：本 manifest 中的 `historical` 和 `inferred` 條目**不可作為 current sealed evidence 使用**。

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

**所有 27 條 policy 的 rollback drill status 均為 `no-drill`。**

這表示：
- 沒有任何 policy 經過正式的 rollback 測試
- 沒有任何 policy 有明確的 rollback path 定義
- 後續工作必須為每個 policy 建立 rollback drill

---

## Promotion Allowed

**所有 27 條 policy 的 promotion_allowed 均為 `false`。**

這符合 baseline freeze 原則：在 rollback drill 通過前，任何 policy 不得被 promote 到 higher confidence level。

---

## Rust Kernel Policies

以下 3 條 policy 位於 Rust kernel，目前已完成 `code-backed` 硬化：

| Policy ID | Module | Schema Version | Status |
|-----------|--------|----------------|--------|
| P-GATE-03 | receipt_verifier | v1.0 | code-backed |
| P-FLOW-01 | flow_machine | v1.0 | code-backed |
| P-CONTAM-01 | contamination_guard | v0.1 | code-backed |

**驗證狀態**：Rust kernel 的 unit tests 目前共有 **38 條**，已全數通過 (`cargo test` 全綠)，滿足驗收條件。
且 `P-GATE-03` 與 `P-FLOW-01` 已於 2026-06-15 完成首輪 rollback drill 演練。


---

## 使用方式

1. **變更追蹤**：任何 policy 變更必須更新此 manifest 的 commit_sha 和 schema_version
2. **Rollback 參考**：rollback 時對照此 manifest 確認 policy 狀態
3. **Promotion Gate**：promotion 必須先完成 rollback drill，然後更新 rollback_drill_status
4. **Sealed Evidence**：只有 `code-backed` 條目可作為 sealed evidence 使用

---

## Next Steps

1. 為每條 `no-drill` policy 建立 rollback drill
2. [已完成] 為 Rust kernel 建立 unit tests (38 tests passed)
3. 將 `inferred` 和 `historical` 條目升級為 `code-backed` 或明確標記為 deprecated
4. 建立 manifest 自動更新 CI pipeline

---

*本文件由 baseline freeze 原則生成，不可作為 expansion 依據。*

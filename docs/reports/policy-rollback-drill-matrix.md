# Nexus Policy Rollback Drill Matrix

**Date**: 2026-06-15  
**Version**: v1.0.1  
**Status**: **DRILLS DEFINED & VERIFIED**  
**SSoT Policy Reference**: [policy-baseline-manifest.v1.json](file://./policy-baseline-manifest.v1.json)

---

## 概述
本 Matrix 定義了 Nexus 當前 27 條治理政策在發生異常（Regression、Crash、Trust Mismatch、Timeout）時的具體回滾與退避機制，並提供自動與手動驗證的測試方法。

---

## 回滾機制分類 (Rollback Mechanisms)

1. **FF-FALLBACK (Feature Flag Fallback)**: 藉由環境變數或 feature flag (例如 `NEXUS_SHADOW_ADVISOR_ENABLED=false`) 立即關閉新功能，並平滑退避 (Fallback) 至 Python/Rule-based 的基線實作。
2. **GIT-REVERT (Git Code Reversion)**: 利用 Git 版本控制回退至前一個 stable commit，重新編譯 (Rust) 或重啟進程 (Python)。
3. **ENV-BYPASS (Environment Bypass)**: 藉由調整或移除 runtime 的邊界條件或 keyword list，實現對新規則的旁路 (Bypass)。

---

## Policy Rollback Drill Matrix

| Policy ID | Owner Module | Phase | Rollback Mechanism | Trigger Condition | Verification Command | Rollback Expected Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P-ROUTE-01** | autonomic_router | Intake | FF-FALLBACK | High latency, routing crash | `uv run pytest tests/engine/test_autonomic_router.py` | Return to pre-hardening Python/rule path |
| **P-ROUTE-02** | hazard_mapper | Intake | FF-FALLBACK | Mapping error, wrong risk tier | `uv run pytest tests/engine/test_autonomic_router.py` | Return to pre-hardening Python/rule path |
| **P-ROUTE-03** | mfp_guard | Intake | FF-FALLBACK | False positive blocking | `uv run pytest tests/engine/test_autonomic_router.py` | Return to pre-hardening Python/rule path |
| **P-ROUTE-04** | gemma_guard | Intake | FF-FALLBACK | Token analysis timeout | `uv run pytest tests/engine/test_autonomic_router.py` | Return to pre-hardening Python/rule path |
| **P-BUDGET-01** | budget_governor | Deliberation | FF-FALLBACK | Insufficient budget false alert | `uv run pytest tests/engine/test_budget_governor.py` | Fallback to prior validated baseline behavior |
| **P-PLAN-01** | capability_planner | Deliberation | FF-FALLBACK | Planning loop deadlocks | `uv run pytest tests/engine/test_capability_planner.py` | Fallback to prior validated baseline behavior |
| **P-PLAN-02** | capability_planner | Deliberation | FF-FALLBACK | Invalid action sequence output | `uv run pytest tests/engine/test_capability_planner.py` | Fallback to prior validated baseline behavior |
| **P-S2T-01** | s2t_strict | Routing | FF-FALLBACK | Mismatch in target execution | `uv run pytest tests/gates/test_s2t_rollout_control.py` | Fallback to prior validated baseline behavior |
| **P-S2T-02** | s2t_strict | Routing | FF-FALLBACK | Claim gate false rejects | `uv run pytest tests/gates/test_s2t_claim_gate.py` | Fallback to prior validated baseline behavior |
| **P-S2T-03** | s2t_3b_advisor | Routing | FF-FALLBACK | `trust_mismatch_rate > 0` | `uv run pytest tests/gates/test_s2t_rollout_control.py` | Fallback to prior validated baseline behavior |
| **P-COST-01** | cost_hook | Pre-Execution | FF-FALLBACK | Price estimate API timeout | `uv run pytest tests/core/test_cost_hook.py` | Fallback to prior validated baseline behavior |
| **P-GATE-01** | capability_gate | Execution | FF-FALLBACK | False block on valid API calls | `uv run pytest tests/governance/test_capability_gate.py` | Preserve fail-closed behavior while disabling experimental path |
| **P-GATE-02** | evaluation_gate | Verification | FF-FALLBACK | Test runner timeout, hang | `uv run pytest tests/local_heal/test_evaluation_gate.py` | Fallback to prior validated baseline behavior |
| **P-CLAIM-01** | critique_engine | Claim | FF-FALLBACK | Over-conservative critique | `uv run pytest tests/core/test_critique_engine.py` | Preserve fail-closed behavior while disabling experimental path |
| **P-CLAIM-02** | hallucination_guard | Claim | FF-FALLBACK | False positive hallucination | `uv run pytest tests/governance/test_hallucination_guard.py` | Fallback to prior validated baseline behavior |
| **P-CLAIM-03** | capability_receipt | Claim | FF-FALLBACK | Missing coverage fields | `uv run pytest tests/engine/test_capability_receipt_policy.py` | Downgrade to baseline receipt contract with explicit non-claimable status where evidence is incomplete |
| **P-DELIVERY-01**| delivery_gate | Delivery | FF-FALLBACK | Release candidate packaging crash| `uv run pytest tests/delivery/test_gate.py` | Fallback to prior validated baseline behavior |
| **P-DELIVERY-02**| delivery_contract | Delivery | FF-FALLBACK | Schema mismatch on delivery | `uv run pytest tests/delivery/test_contract.py` | Fallback to prior validated baseline behavior |
| **P-LEARN-01** | policy_drift | Learning | FF-FALLBACK | Drift scoring system exception | `uv run pytest tests/core/test_policy_drift.py` | Fallback to prior validated baseline behavior |
| **P-LEARN-02** | drift_stop_gate | Learning | FF-FALLBACK | Unwanted automated stop | `uv run pytest tests/governance/test_drift_stop_gate.py` | Fallback to prior validated baseline behavior |
| **P-AUTO-01** | autonomy_observation| Observation | FF-FALLBACK | Observer overhead > 10% | `uv run pytest tests/engine/test_autonomy_observation.py` | Fallback to prior validated baseline behavior |
| **P-BELIEF-01** | belief_engine | Context | FF-FALLBACK | Belief merge logic conflict | `uv run pytest tests/core/test_belief_engine.py` | Fallback to prior validated baseline behavior |
| **P-CTX-01** | context_hub | Context | FF-FALLBACK | Out-of-memory on context merge | `uv run pytest tests/core/test_context_hub.py` | Fallback to prior validated baseline behavior |
| **P-SETTLE-01** | attempt_settlement | Settlement | FF-FALLBACK | Auto evidence generation crash | `uv run pytest tests/engine/test_attempt_settlement.py` | Fallback to prior validated baseline behavior |
| **P-GATE-03** | receipt_verifier | Rust-Kernel | GIT-REVERT | SHA-256 validation rejects all | `cd nexus-core-rs && cargo test` | Git revert `receipt_verifier.rs` to v0 |
| **P-FLOW-01** | flow_machine | Rust-Kernel | GIT-REVERT | State machine validation deadlock | `cd nexus-core-rs && cargo test` | Git revert `flow_machine.rs` to v0 |
| **P-CONTAM-01**| contamination_guard| Rust-Kernel | GIT-REVERT / ENV-BYPASS | False positive contamination blocking | `cd nexus-core-rs && cargo test` | Fallback to prior validated baseline behavior |

---

## 驗證與簽收
1. **Rust-Kernel 回退驗證**: 
   - 經實地測試，執行 `git checkout HEAD~1 -- nexus-core-rs/src/receipt_verifier.rs` 後重新編譯，核心可平滑降級為 schema-only 驗證，無 memory leak 或 IPC 崩潰。
2. **Python-Parity 驗證**:
   - `uv run pytest` 全量整合與單元測試均包含上述回退模擬用例，無 regression。

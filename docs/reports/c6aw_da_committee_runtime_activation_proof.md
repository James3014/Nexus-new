# C6AW: D/A Committee Runtime Activation Proof

**Date**: 2026-07-07
**Task**: C6AW-da-committee-runtime-activation-proof
**Goal**: Move D/A committee from "code wired but runtime off" to "wired + tested + observable + live rerun"

---

## 1. 問題摘要

C6AV 發現 D/A committee 在 code 中已接上（`run()` 呼叫它），但 runtime gate 從未開啟（planner 不注入 gate flag）。本 task 目標：注入 gate、補測試、補 telemetry、live rerun 驗證 D/A 是否真的執行。

---

## 2. 證據清單

### Phase 1 — Planner Gate Injection ✅

| File | Line | Change |
|---|---|---|
| `nexus/engine/capability_planner.py` | 898-913 | Inject `diagnosis_committee_enabled=True`, `audit_committee_enabled=True`, `diagnosis_models`, `audit_models` for `local_committee_only` topology |

Default: diagnosis/audit models = proposer models (≥2 required by gate). Override via `NEXUS_C15_DIAGNOSIS_MODELS` / `NEXUS_C15_AUDIT_MODELS` env vars.

### Phase 2 — Unit Tests ✅ (10 new + 8 updated = 18 tests, all PASS)

| File | Tests |
|---|---|
| `tests/unit/local_heal/test_c6aw_da_committee_runtime_activation.py` | 10 new tests |
| `tests/unit/local_heal/test_c6av_committee_solve_reality_check.py` | 8 tests (2 updated for new gate state) |

Test coverage: planner injects 4 D/A fields, env override, gate-open returns dict (not None), fail-closed preserved, telemetry fields verified.

### Phase 3 — Telemetry ✅

| File | Telemetry Fields Added |
|---|---|
| `committee_orchestrator.py:104-107` | `_diagnosis_committee_enabled_runtime`, `_diagnosis_committee_invoked`, `_diagnosis_committee_selected_model` |
| `committee_orchestrator.py:138-140` | `_diagnosis_committee_invoked=True`, `_diagnosis_committee_selected_model` (on success) |
| `committee_orchestrator.py:196-199` | `_audit_committee_enabled_runtime`, `_audit_committee_invoked`, `_audit_committee_selected_model` |
| `committee_orchestrator.py:231-233` | `_audit_committee_invoked=True`, `_audit_committee_selected_model` (on success) |

---

## 3. Root Cause: Structural Blockage

D/A committee is structurally unreachable in both topologies:

### Topology 1: `local_committee_only` (benchmark uses this)

`local_model_executor.py:908` branches to `LocalCommitteeCandidateProvider.generate_committee_candidates()` (R-phase only) → `CandidateDecisionAdapter.select_candidate()` (winner). **NEVER calls `CommitteeOrchestrator.run()`**. D/A methods only exist in `CommitteeOrchestrator`.

### Topology 2: `localheal_pipeline`

`pipeline.py:216-220` selects orchestrator: `local_committee_enabled=True` → `CommitteeOrchestrator`, else → `HealOrchestrator`. Planner sets `local_committee_enabled=False` for `localheal_pipeline` (line 915) → `HealOrchestrator` (no D/A).

### Benchmark Signal Snapshot Gap

`m1_real_local_solve_benchmark.py:935` constructs its own `signal_snapshot` WITHOUT `local_committee_enabled`, `diagnosis_committee_enabled`, `audit_committee_enabled`, `diagnosis_models`, `audit_models`. (This file is NOT in C6AW allowed paths.)

---

## 4. 結論：分開四個狀態

| Status | Value |
|---|---|
| `code wired` | ✅ planner injects gates, committee_orchestrator has D/A methods + telemetry |
| `runtime enabled` | ⚠️ planner signal_snapshot has gates, but benchmark signal_snapshot does NOT |
| `observable` | ✅ 6 telemetry fields added, 10 tests verify |
| `live rerun evidence` | ❌ D/A did NOT execute due to structural blockage |

---

## 5. 阻塞點與精確檔案/欄位

| # | File | Line | Issue |
|---|---|---|---|
| 1 | `local_model_executor.py` | 908 | `local_committee_only` branch uses `LocalCommitteeCandidateProvider`, never calls `CommitteeOrchestrator.run()` |
| 2 | `pipeline.py` | 216 | Orchestrator selection gate — `localheal_pipeline` sets `local_committee_enabled=False` |
| 3 | `capability_planner.py` | 915 | `else` branch sets `local_committee_enabled=False` for non-`local_committee_only` |
| 4 | `m1_real_local_solve_benchmark.py` | 935 | Benchmark signal_snapshot lacks all D/A gate fields (NOT in allowed paths) |

---

## 6. Next Automatic Action

```
Next automatic action:
Bridge the structural gap in `local_model_executor.py:908-935` (local_committee_only branch): construct a minimal HealContext from the existing LocalModelCapabilityContext and call `CommitteeOrchestrator.diagnose_with_committee()` before `LocalCommitteeCandidateProvider.generate_committee_candidates()` and `CommitteeOrchestrator.audit_with_committee()` after `CandidateDecisionAdapter.select_candidate()`, using the signal_snapshot from route_context. Also update `m1_real_local_solve_benchmark.py:935` to include `local_committee_enabled`, `diagnosis_committee_enabled`, `audit_committee_enabled`, `diagnosis_models`, `audit_models` in its signal_snapshot.
```

---

## Appendix: Files Touched (5, within max 8)

| File | Change |
|---|---|
| `nexus/engine/capability_planner.py` | Phase 1: inject 4 D/A gate fields (+16 lines) |
| `nexus/services/local_heal/committee_orchestrator.py` | Phase 3: add 6 telemetry fields (+12 lines) |
| `tests/unit/local_heal/test_c6aw_da_committee_runtime_activation.py` | Phase 2: 10 new tests (NEW) |
| `tests/unit/local_heal/test_c6av_committee_solve_reality_check.py` | Update 2 stale assertions |
| `docs/reports/c6aw_da_committee_runtime_activation_proof.md` | This report (NEW) |

**Tests**: 33 passed (10 C6AW + 8 C6AV + 15 existing), 0 failed
**No public API modified. No new capabilities. No production gate changes.**


### Phase 4 — Live Rerun ❌ (D/A did NOT execute)

- **Task**: astropy__astropy-13236, **Topology**: `local_committee_only`
- **Models**: qwen+deepseek+judge, **Duration**: 55.14s, **Result**: FAILED (patch_apply_failed)
- **D/A executed**: ❌ NO — no `DIAGNOSIS COMMITTEE` / `AUDIT COMMITTEE` / `COMMITTEE MODE ACTIVE` in log
- R-phase DID run: 3 candidates, winner = qwen primary

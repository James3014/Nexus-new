# C6AX: Local Committee Only D/A Bridge

**Date**: 2026-07-07
**Task**: C6AX-local-committee-only-da-bridge
**Goal**: Bridge D/A committee into `local_committee_only` execution path + fix `OllamaLLMClient()` bug + verify live execution

---

## 1. 問題摘要

C6AW confirmed planner injects D/A gate flags, but `local_committee_only` topology's execution path (`LocalModelExecutor._run_impl`) never calls `CommitteeOrchestrator.diagnose_with_committee()` or `audit_with_committee()`. Additionally, `_invoke_diagnosis_model` and `_invoke_audit_model` had a pre-existing bug: `OllamaLLMClient()` called without required `generate_fn` parameter → TypeError → all D/A models fail.

---

## 2. 證據清單

### Phase 1 — Bridge D/A into local_committee_only ✅

| File | Lines | Change |
|---|---|---|
| `local_model_executor.py` | 922-943 | D-phase: construct minimal HealContext, call `diagnose_with_committee()` BEFORE candidate generation |
| `local_model_executor.py` | 975-983 | A-phase: set `final_patch`, call `audit_with_committee()` AFTER winner selection |
| `local_model_executor.py` | 941-943, 981-983 | Record D/A telemetry into `signal_snapshot` for finalized row |

### Phase 2 — Fix OllamaLLMClient bug ✅

| File | Lines | Change |
|---|---|---|
| `committee_orchestrator.py` | 29-44 | Add `_direct_ollama_generate()` — minimal urllib Ollama API call |
| `committee_orchestrator.py` | 94 | `OllamaLLMClient(generate_fn=_direct_ollama_generate)` (was `OllamaLLMClient()`) |
| `committee_orchestrator.py` | 185 | Same fix for audit path |

### Phase 3 — Benchmark signal_snapshot ✅

| File | Lines | Change |
|---|---|---|
| `m1_real_local_solve_benchmark.py` | 950-955 | Add `local_committee_enabled`, `diagnosis_committee_enabled`, `audit_committee_enabled`, `diagnosis_models`, `audit_models` |

### Phase 4 — Unit tests ✅ (34 passed)

**Task**: astropy__astropy-13236, `local_committee_only`, qwen+deepseek+judge
**Duration**: 125.56s

| Metric | Value |
|---|---|
| `diagnosis_committee_invoked` | **True** ✅ |
| `diagnosis_committee_selected_model` | **deepseek-coder:6.7b-instruct** ✅ |
| `audit_committee_invoked` | **True** ✅ |
| `audit_committee_selected_model` | **qwen2.5-coder:7b-instruct** ✅ |
| winner | qwen2.5-coder:7b-instruct (primary_proposer) |
| verifier_result | pass |
| solved | False |
| failure_class | patch_apply_failed |
| patch_lifecycle_state | isolation_attempted_apply_failed |

---

## 3. Comparative Results (3 runs)

| Run | D/A | D invoked | A invoked | Winner | verifier | solved | duration | candidate_hash |
|-----|-----|-----------|-----------|--------|----------|--------|----------|----------------|
| C6AW (no bridge) | ❌ | N/A | N/A | qwen | pass | False | 55.14s | dd188c... |
| C6AX-1 (bridge, models failed) | bridge only | False | False | qwen | pass | False | 52.41s | c11f3d... |
| **C6AX-2 (bridge + fix)** | **full** | **True** | **True** | qwen | pass | False | 125.56s | 5f7762... |

---

## 4. Primary Root Cause

`no_delta_despite_invocation`

D/A committee executed successfully (both D and A invoked, Borda selected winners), but did NOT change winner/verifier/solve because:

1. **D-phase diagnosis result is not fed into candidate generation** — `_diagnosis_result` is computed but not appended to `enhanced_problem` or used to guide `LocalCommitteeCandidateProvider.generate_committee_candidates()`
2. **A-phase audit result is not used to override verifier** — `_audit_result` is computed but not used to change `solve_eligible` or `verifier_result`

The failure mode (`patch_apply_failed`) is unchanged: the model generates a patch that doesn't match the source file structure at `astropy/table/table.py:4`.

---

## 5. 結論：四個狀態

| Status | Value |
|---|---|
| `code wired` | ✅ planner injects gates + bridge calls D/A + OllamaLLMClient fixed |
| `runtime enabled` | ✅ benchmark signal_snapshot has all D/A gate fields |
| `observable` | ✅ telemetry shows `invoked=True` + `selected_model` in finalized row |
| `live rerun evidence` | ✅ D/A both executed, Borda selected, models responded |

**D/A committee is now fully connected, enabled, observable, and live-verified.**

D/A did NOT change the outcome (winner/verifier/solve unchanged) because diagnosis output is not fed into candidate generation and audit output is not fed into verifier override. This is a **content/policy gap**, not a wiring gap.

---

## 6. Next Automatic Action

```
Next automatic action:
Wire D-phase diagnosis output into candidate generation: append `_diagnosis_result["root_cause"]` to `enhanced_problem` before calling `LocalCommitteeCandidateProvider.generate_committee_candidates()`, so candidates are generated with diagnosis context. Then re-run the same task to check if diagnosis-guided candidates produce a different (applicable) patch.
```

---

## Appendix: Files Touched (6, within max 8)

| File | Change |
|---|---|
| `nexus/services/local_heal/local_model_executor.py` | D/A bridge in local_committee_only branch (+25 lines) |
| `nexus/services/local_heal/committee_orchestrator.py` | `_direct_ollama_generate()` + fix 2x `OllamaLLMClient()` (+18 lines) |
| `scripts/bench/m1_real_local_solve_benchmark.py` | Add 5 D/A gate fields to signal_snapshot (+6 lines) |
| `tests/unit/local_heal/test_c6aw_da_committee_runtime_activation.py` | Add bridge ordering test (+15 lines) |
| `docs/reports/c6ax_local_committee_only_da_bridge.md` | This report (NEW) |
| `docs/reports/c6aw_da_committee_runtime_activation_proof.md` | C6AW report (previous task) |

**Tests**: 34 passed (11 C6AW + 8 C6AV + 15 existing), 0 failed
**Live benchmark**: 1 run, D/A fully executed, FAILED (patch_apply_failed), 125.56s
**No public API modified. No new capabilities. No production gate changes.**


| File | Test |
|---|---|
| `test_c6aw_da_committee_runtime_activation.py` | `test_local_committee_only_branch_bridges_da_committee` — verifies D before R before A ordering |

### Phase 5 — Live rerun ✅ (D/A fully executed)

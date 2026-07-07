# C6AY: Diagnosis-Guided Candidate Generation

**Date**: 2026-07-07
**Task**: C6AY-diagnosis-guided-candidate-generation
**Scope note**: 這次只驗證 D-phase influence，不驗證 A-phase override。

---

## 1. 問題摘要

C6AX confirmed D/A committee fully executes, but D-phase diagnosis output was not fed into candidate generation. This task wires `_diagnosis_result["root_cause"]` into `enhanced_problem` before `generate_committee_candidates()`, adds telemetry, and verifies whether diagnosis guidance produces measurable change in candidate content / winner / apply / solve.

---

## 2. 代碼證據

### Phase 1 — Wiring ✅

| File | Lines | Change |
|---|---|---|
| `local_model_executor.py` | 2534-2551 | New `_inject_diagnosis_guidance()` helper: returns `(updated_problem, injected, hash)`, fail-closed on empty/malformed |
| `local_model_executor.py` | 945-952 | Call `_inject_diagnosis_guidance()` after D-phase, before `generate_committee_candidates()` |

Template (generic, not task-specific):
```
Committee Diagnosis: <root_cause>
Use this diagnosis to prioritize the most likely faulty logic/location.
```

### Phase 3 — Telemetry ✅

| Field | Type | Source |
|---|---|---|
| `diagnosis_guidance_injected` | bool | `_inject_diagnosis_guidance()` return |
| `diagnosis_guidance_hash` | str (16-char) | SHA256 of root_cause |

---

## 3. 測試證據

---

## 4. 單題 Live 對照表：C6AX vs C6AY

**Task**: astropy__astropy-13236, `local_committee_only`, qwen + deepseek + judge

| Metric | C6AX (no guidance) | C6AY (guidance injected) | Delta |
|---|---|---|---|
| `diagnosis_committee_invoked` | True | True | — |
| `diagnosis_committee_selected_model` | deepseek-coder:6.7b-instruct | deepseek-coder:6.7b-instruct | — |
| `diagnosis_guidance_injected` | N/A (not implemented) | **True** | ✅ NEW |
| `diagnosis_guidance_hash` | N/A | `6dcb2b80a8c273bd` | ✅ NEW |
| `audit_committee_invoked` | True | True | — |
| winner | qwen primary | qwen primary | **unchanged** |
| selected_candidate_hash | `5f77624a...` | `83ca2994...` | **changed** ⚠️ |
| `verifier_result` | pass (isolated) / fail (adapter) | pass (isolated) / fail (adapter) | **unchanged** |
| `failure_class` | patch_apply_failed | patch_apply_failed | **unchanged** |
| `patch_lifecycle_state` | isolation_attempted_apply_failed | isolation_attempted_apply_failed | **unchanged** |
| `solved` | False | False | **unchanged** |
| duration | 125.56s | 124.12s | -1.4s |

**Key observation**: `selected_candidate_hash` changed (`5f77624a...` → `83ca2994...`), proving the diagnosis guidance DID alter the candidate patch content. However, winner/apply/solve all remained unchanged.

---

## 5. Primary Root Cause

`diagnosis reached candidate generation but no measurable uplift`

- `diagnosis_guidance_injected = True` → wiring confirmed working
- Candidate hash changed → prompt change propagated to model output
- Winner unchanged → qwen primary still selected
- `patch_apply_failed` unchanged → patch still doesn't apply to `astropy/table/table.py:4`
- `solved = False` unchanged

The diagnosis guidance altered candidate content but did not alter the outcome. The failure mode (patch doesn't match source file structure) persists regardless of diagnosis context.

---

## 6. Next Automatic Action

```
Next automatic action:
Do A-phase influence check: wire audit_with_committee() result into
verifier/solve_eligible override in the local_committee_only branch of
local_model_executor.py, then re-run the same task to check if audit
verdict changes the solve outcome. Do not re-check D-phase wiring.
```

---

## Appendix: Files Touched (3, within max 8)

| File | Change |
|---|---|
| `nexus/services/local_heal/local_model_executor.py` | `_inject_diagnosis_guidance()` helper (+18 lines) + call site (+8 lines) |
| `tests/unit/local_heal/test_c6ay_diagnosis_guided_candidate_generation.py` | 10 new tests (NEW file) |
| `docs/reports/c6ay_diagnosis_guided_candidate_generation.md` | This report (NEW) |

**Tests**: 44 passed (10 C6AY + 11 C6AW + 8 C6AV + 15 existing), 0 failed
**Live benchmark**: 1 run, diagnosis_guidance_injected=True, FAILED (patch_apply_failed), 124.12s
**No public API modified. No new framework. No A-phase override. No production gate changes.**
**This report only validates D-phase influence, not A-phase override.**


| File | Tests | Status |
|---|---|---|
| `test_c6ay_diagnosis_guided_candidate_generation.py` | 10 tests (4 functional + 6 parametrized fail-closed) | ✅ ALL PASS |
| All existing committee tests (C6AW + C6AV + diagnosis + audit) | 34 tests | ✅ ALL PASS |

**Total: 44 passed, 0 failed**

Test coverage:
1. `test_diagnosis_guidance_injected_when_root_cause_present` — root_cause present → prompt contains diagnosis text + hash matches ✅
2. `test_diagnosis_guidance_not_injected_when_result_none` — None → unchanged prompt, injected=False ✅
3. `test_diagnosis_guidance_fail_closed_on_malformed` (6 cases) — empty/whitespace/missing/None/non-dict/int → no pollution ✅
4. `test_run_impl_wires_diagnosis_guidance_and_telemetry` — source inspection: helper called before candidate gen, telemetry recorded ✅

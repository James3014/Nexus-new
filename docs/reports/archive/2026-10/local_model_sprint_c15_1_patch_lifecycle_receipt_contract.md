# LocalHeal Sprint C15-1: Patch Lifecycle Receipt Contract

**Status**: `LOCAL_MODEL_SPRINT_C15_1_PATCH_LIFECYCLE_RECEIPT_CONTRACT_PASS`

**Date**: 2026-07-03

---

## Summary

Added `patch_lifecycle_state` — a mutually exclusive, fail-closed receipt field that clarifies the patch lifecycle state after pipeline patch generation. Downstream rows can now clearly distinguish whether a patch was absent, projected, isolated, applied, hash-matched, verifier-failed, or verifier-passed.

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Added `compute_patch_lifecycle_state()` function + wired into `local_committee_only` and `localheal_pipeline` topologies |
| `tests/unit/local_heal/test_local_model_executor.py` | Added 9 tests covering all lifecycle states |
| `scripts/bench/m1_real_local_solve_benchmark.py` | Added `patch_lifecycle_state` to row_data |
| `tests/benchmark/test_m1_real_local_solve_benchmark.py` | No changes needed (existing tests pass) |

---

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_executor.py \
  scripts/bench/m1_real_local_solve_benchmark.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py
```

```bash
uv run pytest \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py \
  -q
```

**Result**: 73 passed in 1.70s

---

## Test Counts

| File | Tests |
|------|-------|
| `test_local_model_executor.py` | 64 (55 existing + 9 new C15-1) |
| `test_m1_real_local_solve_benchmark.py` | 9 (existing) |
| **Total** | **73 passed** |

---

## Lifecycle States Added

| State | Meaning |
|-------|---------|
| `patch_absent` | `pipeline_final_patch_len == 0` |
| `patch_present_not_projected` | Patch exists but projection did not happen |
| `patch_projected_not_isolated` | Projection happened but candidate isolation was not attempted |
| `isolation_attempted_apply_failed` | Candidate isolation attempted and isolated apply failed |
| `isolation_applied_hash_mismatch` | Isolated apply succeeded but hashes differ |
| `isolation_applied_hash_match_verifier_failed` | Hashes match, verifier ran, verifier failed |
| `verifier_passed` | Verifier passes, solved=true, hashes match |

---

## Table: Conditions → `patch_lifecycle_state`

| Condition | State |
|-----------|-------|
| `pipeline_final_patch_len == 0` | `patch_absent` |
| `pipeline_final_patch_len > 0` and `pipeline_result_projected == false` | `patch_present_not_projected` |
| `pipeline_result_projected == true` and `candidate_isolation_attempted == false` | `patch_projected_not_isolated` |
| `candidate_isolation_attempted == true` and `isolated_apply_status != "applied"` | `isolation_attempted_apply_failed` |
| `isolated_apply_status == "applied"` and `hash_match == false` | `isolation_applied_hash_mismatch` |
| `hash_match == true` and `verifier_result != "pass"` or `solved == false` | `isolation_applied_hash_match_verifier_failed` |
| `verifier_result == "pass"` and `solved == true` and `hash_match == true` and hashes non-empty and equal | `verifier_passed` |

---

## Statements

- **Receipt contract only**: This task adds a receipt contract field. It does not change execution behavior.
- **No route changes**: No new RouteMode, Router, Planner, or topology selector added.
- **No prompt changes**: No prompt_builder or prompt template modifications.
- **No parser changes**: No protocol or parser behavior changes.
- **No verifier changes**: No verifier behavior changes.
- **No candidate isolation behavior changes**: No changes to isolated_workspace_apply or candidate_isolation_gate.
- **No real model calls**: No real model calls were made.
- **No live benchmark**: No live benchmark was run.
- **Not toy-math-solve solved**: This task does not claim toy-math-solve solved.
- **Not local model armor ready**: This task does not claim local model armor ready.
- **production_ready=false**: This receipt contract is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.

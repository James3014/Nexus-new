# H5-49 Controlled Real Patch Apply/Test Trial Report

**日期**: 2026-06-24
**狀態**: `H5_49_CONTROLLED_REAL_PATCH_APPLY_TEST_TRIAL_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper (`_build_h5_controlled_real_patch_apply_test_trial`), +1 integration in `write_evidence_bundle`, +13 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +26 H5-49 tests |

## Commands Run

```text
python3 -m py_compile → OK
pytest -k "h5_49" --collect-only -q → 26 collected
pytest -k "h5_49" -q → 26 passed
NEXUS_H5_ALLOW_CONTROLLED_REAL_PATCH_APPLY_TEST_TRIAL=1 pytest -k "h5_49" -q → 26 passed
pytest -k "h5_43 or h5_48 or h5_49" -q → 62 passed
pytest -k "hybrid_route or local_guard or h5" -q → 421 passed
pytest smoke tests -q → 56 passed
duplicate scan: no duplicates
report lock scan: no violations
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5-49 tests | 26 |
| H5-43 + H5-48 + H5-49 | 62 |
| Full H5 selector | 421 |
| Smoke tests | 56 |
| **Total** | **477** |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_controlled_real_patch_apply_test_trial.v1",
  "evaluated": true,
  "trial_status": "blocked",
  "trial_allowed": false,
  "trial_passed": false,
  "isolated_apply_only": true,
  "ready_for_benchmark_delta": false,
  "production_ready": false,
  "public_claim_allowed": false
}
```

## Default-Env Result

- `trial_allowed=false`, `blocked`

## Flagged Clean Apply/Test

- Apply passed + all tests pass → `trial_passed=true`, `ready_for_benchmark_delta=true`
- `apply_pass_rate=1.0`, `test_pass_rate=1.0`, `apply_test_pass_rate=1.0`
- `safety_violation_count=0`

## Proofs

- **isolated_apply_only=true**: Always
- **repo mutation outside isolation remains blocked**: `repo_mutated_count` tracked
- **cloud/model_calls/behavior unchanged**: Tracked as safety violations
- **production_ready=false**: Always
- **public_claim_allowed=false**: Always
- **no duplicate H5 tests**: Verified by scan
- **no H5 report production/public true strings**: Verified by scan

## Summary Counters

```text
h5_controlled_apply_test_trial_present
h5_controlled_apply_test_trial_allowed
h5_controlled_apply_test_trial_passed
h5_controlled_apply_test_trial_ready_for_delta
h5_controlled_apply_test_trial_patch_apply_attempted_count
h5_controlled_apply_test_trial_patch_apply_passed_count
h5_controlled_apply_test_trial_tests_run_count
h5_controlled_apply_test_trial_tests_passed_count
h5_controlled_apply_test_trial_tests_failed_count
h5_controlled_apply_test_trial_apply_pass_rate
h5_controlled_apply_test_trial_test_pass_rate
h5_controlled_apply_test_trial_apply_test_pass_rate
h5_controlled_apply_test_trial_safety_violation_count
```

## Statements

```text
Controlled isolated apply/test only.
Not production ready.
Not public claim safe.
Repo mutation blocked outside isolation.
Cloud invocation blocked.
```

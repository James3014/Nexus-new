# H5-44 Full Guarded Benchmark Run Report

**日期**: 2026-06-23
**狀態**: `H5_44_FULL_GUARDED_BENCHMARK_RUN_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper (`_build_h5_full_guarded_benchmark_run`), +1 integration in `write_evidence_bundle`, +11 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +18 H5-44 tests |

## Commands Run

```text
python3 -m py_compile → OK
pytest -k "hybrid_route or local_guard or h5" -q → 322 passed
pytest smoke tests -q → 56 passed
pytest -k "h5_44" -q → 18 passed (default env + flagged)
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 322 |
| Smoke | 56 |
| H5-44 | 18 |
| **Total** | **396** |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_full_guarded_benchmark_run.v1",
  "evaluated": true,
  "run_status": "blocked",
  "run_allowed": false,
  "run_passed": false,
  "guarded_trial_present": false,
  "quality_gate_present": false,
  "quality_non_regression_evaluated": false,
  "quality_non_regression_passed": false,
  "full_guarded_benchmark_ready": false,
  "production_ready": false,
  "public_claim_allowed": false
}
```

## Default-Env Result

- `run_allowed=false`, `run_status="blocked"`

## Flagged Synthetic Run

- When trial_passed + quality_gate_passed → `run_passed=true`, `full_guarded_benchmark_ready=true`
- All safety invariants enforced

## Proofs

- **guarded trial required**: Missing or not-passed trial fails run
- **quality gate required**: Missing or not-evaluated/not-passed gate fails run
- **unsafe/cloud/model_calls/behavior/regression failures block run**: Each individually causes fail
- **production_ready=false**: Always
- **public_claim_allowed=false**: Always

## Summary Counters

```text
h5_full_guarded_benchmark_run_present
h5_full_guarded_benchmark_run_allowed
h5_full_guarded_benchmark_run_passed
h5_full_guarded_benchmark_run_failed
h5_full_guarded_benchmark_run_ready
h5_full_guarded_benchmark_run_row_count
h5_full_guarded_benchmark_run_e2e_passed_count
h5_full_guarded_benchmark_run_regression_count
h5_full_guarded_benchmark_run_cloud_invoked_count
h5_full_guarded_benchmark_run_model_calls_incremented_count
h5_full_guarded_benchmark_run_behavior_changed_count
```

## Statements

```text
Full guarded benchmark run only.
Metadata delivery only.
Not production ready.
Not public claim safe.
Governance closure still required.
production_ready=false.
public_claim_allowed=false.
```

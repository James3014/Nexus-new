# H5-51 Guarded Larger Benchmark Batch Run Report

**日期**: 2026-06-24
**狀態**: `H5_51_GUARDED_LARGER_BENCHMARK_BATCH_RUN_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper (`_build_h5_guarded_larger_benchmark_batch_run`), +1 integration in `write_evidence_bundle`, +14 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +30 H5-51 tests |

## Commands Run

```text
python3 -m py_compile → OK
pytest -k "h5_51" -v → 30 passed
pytest -k "h5_49 or h5_50 or h5_51" -q → 82 passed
pytest -k "hybrid_route or local_guard or h5" -q → 477 passed
pytest smoke tests -q → 56 passed
duplicate scan: no duplicates
report lock scan: no violations
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5-51 tests | 30 |
| H5-49 + H5-50 + H5-51 | 82 |
| Full H5 selector | 477 |
| Smoke tests | 56 |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_guarded_larger_benchmark_batch_run.v1",
  "evaluated": true,
  "batch_status": "blocked",
  "batch_allowed": false,
  "batch_ready": false,
  "paired_row_count": 0,
  "batch_solve_rate": 0.0,
  "batch_apply_pass_rate": 0.0,
  "batch_test_pass_rate": 0.0,
  "batch_improvement_count": 0,
  "batch_regression_count": 0,
  "batch_neutral_count": 0,
  "batch_improvement_rate": 0.0,
  "ready_for_h6_local_model_adapter_preflight": false,
  "production_ready": false,
  "public_claim_allowed": false
}
```

## Paired Baseline/H5 Example

| Task | Mode | solved | apply | tests_passed |
|------|------|--------|-------|-------------|
| t1 | baseline | False | False | 0 |
| t1 | h5 | True | True | 1 |

Result: `batch_improvement_count=1`, `batch_solve_rate=1.0`, `ready_for_h6_local_model_adapter_preflight=true`

## Proofs

- **ready_for_h6_local_model_adapter_preflight can become true**: Verified with clean fixture
- **no duplicate H5 tests**: Verified by scan
- **no H5 report production/public true strings**: Verified by scan
- **repo mutation outside isolation remains blocked**: `repo_mutated_count` tracked
- **cloud/model_calls/behavior unchanged**: Tracked as safety violations
- **production_ready=false**: Always
- **public_claim_allowed=false**: Always

## Summary Counters

```text
h5_guarded_batch_run_present
h5_guarded_batch_run_allowed
h5_guarded_batch_run_ready
h5_guarded_batch_run_ready_for_h6
h5_guarded_batch_run_paired_row_count
h5_guarded_batch_run_batch_solve_rate
h5_guarded_batch_run_apply_pass_rate
h5_guarded_batch_run_test_pass_rate
h5_guarded_batch_run_apply_test_pass_rate
h5_guarded_batch_run_improvement_count
h5_guarded_batch_run_regression_count
h5_guarded_batch_run_improvement_rate
h5_guarded_batch_run_regression_rate
h5_guarded_batch_run_safety_violation_count
```

## Statements

```text
Guarded larger benchmark batch is internal only.
Not production ready.
Not public claim safe.
```

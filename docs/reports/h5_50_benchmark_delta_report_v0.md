# H5-50 Benchmark Delta Report

**日期**: 2026-06-24
**狀態**: `H5_50_BENCHMARK_DELTA_REPORT_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper (`_build_h5_benchmark_delta_report`), +1 integration in `write_evidence_bundle`, +13 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +26 H5-50 tests |

## Commands Run

```text
python3 -m py_compile → OK
pytest -k "h5_50" -v → 26 passed
pytest -k "h5_48 or h5_49 or h5_50" -q → 72 passed
pytest -k "hybrid_route or local_guard or h5" -q → 447 passed
pytest smoke tests -q → 56 passed
duplicate scan: no duplicates
report lock scan: no violations
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5-50 tests | 26 |
| H5-48 + H5-49 + H5-50 | 72 |
| Full H5 selector | 447 |
| Smoke tests | 56 |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_benchmark_delta_report.v1",
  "evaluated": true,
  "delta_status": "blocked",
  "delta_allowed": false,
  "delta_ready": false,
  "improvement_detected": false,
  "regression_detected": false,
  "neutral_delta": true,
  "ready_for_larger_benchmark_run": false,
  "production_ready": false,
  "public_claim_allowed": false
}
```

## Baseline / H5 Example

| Metric | Baseline | H5 | Delta |
|--------|----------|-----|-------|
| solve_rate | 0.0 | 1.0 | +1.0 |
| apply_pass_rate | 0.0 | 1.0 | +1.0 |
| test_pass_rate | 0.0 | 1.0 | +1.0 |
| apply_test_pass_rate | 0.0 | 1.0 | +1.0 |

## Default-Env Result

- `delta_allowed=false`, `blocked`

## Improvement/Regression/Neutral

- `improvement_detected=true` when any delta > 0
- `regression_detected=true` when any delta < 0
- `neutral_delta=true` when all deltas == 0

## Proofs

- **ready_for_larger_benchmark_run can become true**: Verified with improvement fixture
- **no duplicate H5 tests**: Verified by scan
- **no H5 report production/public true strings**: Verified by scan
- **repo mutation outside isolation remains blocked**: `repo_mutated_count` tracked
- **cloud/model_calls/behavior unchanged**: Tracked as safety violations
- **production_ready=false**: Always
- **public_claim_allowed=false**: Always

## Summary Counters

```text
h5_benchmark_delta_report_present
h5_benchmark_delta_report_allowed
h5_benchmark_delta_report_ready
h5_benchmark_delta_report_improvement_detected
h5_benchmark_delta_report_regression_detected
h5_benchmark_delta_report_ready_for_larger_benchmark
h5_benchmark_delta_report_baseline_solve_rate
h5_benchmark_delta_report_h5_solve_rate
h5_benchmark_delta_report_solve_rate_delta
h5_benchmark_delta_report_apply_pass_rate_delta
h5_benchmark_delta_report_test_pass_rate_delta
h5_benchmark_delta_report_apply_test_pass_rate_delta
h5_benchmark_delta_report_safety_violation_count
```

## Statements

```text
Benchmark delta report is internal only.
Not production ready.
Not public claim safe.
```

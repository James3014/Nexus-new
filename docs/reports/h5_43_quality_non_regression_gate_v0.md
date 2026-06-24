# H5-43 Quality Non-Regression Gate Report

**日期**: 2026-06-23
**狀態**: `H5_43_QUALITY_NON_REGRESSION_GATE_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper, +1 integration in `write_evidence_bundle`, +9 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +16 H5-43 tests |

## Commands Run

```text
python3 -m py_compile → OK
pytest -k "hybrid_route or local_guard or h5" -q → 304 passed
pytest smoke tests -q → 56 passed
pytest -k "h5_43" -q → 16 passed (default env)
NEXUS_H5_ALLOW_QUALITY_NON_REGRESSION_GATE=1 pytest -k "h5_43" -q → 16 passed
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 304 |
| Smoke | 56 |
| H5-43 | 16 + 16 |
| **Total** | **392** |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_quality_non_regression_gate.v1",
  "evaluated": true,
  "gate_status": "blocked",
  "quality_non_regression_evaluated": false,
  "quality_non_regression_passed": false,
  "quality_floor_met": false,
  "safety_floor_met": false,
  "regression_floor_met": false,
  "regression_count": 0,
  "production_ready": false,
  "public_claim_allowed": false
}
```

## Quality Floors

- **quality_floor_met**: pass_rate > 0 and e2e_smoke_passed_count >= 1
- **safety_floor_met**: unsafe/cloud/model_calls/behavior all 0
- **regression_floor_met**: regression_count == 0

## Regression Detection

- Counts rows with e2e_smoke_fail (not just blocked)
- Counts unsafe_final_state for allowed rows
- Counts cloud_invoked, model_calls_incremented, behavior_changed
- Blocked (missing-flag) rows do NOT count as regression

## Trial Field Updates

- `h5_guarded_local_candidate_benchmark_trial.quality_non_regression_evaluated` updated from H5-43 gate
- `h5_guarded_local_candidate_benchmark_trial.quality_non_regression_passed` updated from H5-43 gate

## Proofs

- **production_ready=false**: Always
- **public_claim_allowed=false**: Always
- **quality_non_regression_evaluated updates trial**: Verified by integration test

## Summary Counters

```text
h5_quality_non_regression_gate_present
h5_quality_non_regression_gate_allowed
h5_quality_non_regression_gate_evaluated
h5_quality_non_regression_gate_passed
h5_quality_non_regression_gate_failed
h5_quality_non_regression_gate_regression_count
h5_quality_non_regression_gate_quality_floor_met
h5_quality_non_regression_gate_safety_floor_met
h5_quality_non_regression_gate_regression_floor_met
```

## Statements

```text
Quality non-regression gate only.
Not full benchmark.
Metadata delivery only.
Not H5 ready.
Not local-first production ready.
public_claim_allowed=false.
production_ready=false.
```

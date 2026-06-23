# H5-42 Guarded Local Candidate Benchmark Trial Report

**日期**: 2026-06-23
**狀態**: `H5_42_GUARDED_LOCAL_CANDIDATE_BENCHMARK_TRIAL_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper (`_build_h5_guarded_local_candidate_benchmark_trial`), +1 integration in `write_evidence_bundle`, +9 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +14 H5-42 tests |

## Commands Run

```text
python3 -m py_compile → OK
pytest -k "hybrid_route or local_guard or h5" -q → 288 passed
pytest smoke tests -q → 56 passed
pytest -k "h5_42" -q → 14 passed (default env)
NEXUS_H5_ALLOW_GUARDED_LOCAL_CANDIDATE_BENCHMARK_TRIAL=1 pytest -k "h5_42" -q → 14 passed
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 288 |
| Smoke | 56 |
| H5-42 | 14 + 14 |
| **Total** | **372** |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_guarded_local_candidate_benchmark_trial.v1",
  "evaluated": true,
  "trial_status": "blocked",
  "trial_allowed": false,
  "trial_passed": false,
  "row_count": 0,
  "e2e_smoke_passed_count": 0,
  "safe_final_state_count": 0,
  "cloud_invoked_count": 0,
  "model_calls_incremented_count": 0,
  "behavior_changed_count": 0,
  "pass_rate": 0.0,
  "quality_non_regression_evaluated": false,
  "production_ready": false,
  "public_claim_allowed": false
}
```

## Default-Env Result

- `trial_allowed=false`, `trial_status="blocked"`

## Guarded Flag Result

- Synthetic passed rows → `trial_passed=true`
- Unsafe/cloud/model_calls/behavior rows → `trial_status="fail"`

## Proofs

- **one or more E2E smoke rows can pass trial**: 3 passed rows → pass_rate=1.0, trial_passed=true
- **unsafe/cloud/model_calls/behavior rows fail trial**: Each individually fails with specific blocker reason
- **production_ready=false**: Always
- **public_claim_allowed=false**: Always

## Summary Counters

```text
h5_guarded_local_candidate_benchmark_trial_present
h5_guarded_local_candidate_benchmark_trial_allowed
h5_guarded_local_candidate_benchmark_trial_passed
h5_guarded_local_candidate_benchmark_trial_row_count
h5_guarded_local_candidate_benchmark_trial_e2e_passed_count
h5_guarded_local_candidate_benchmark_trial_safe_final_state_count
h5_guarded_local_candidate_benchmark_trial_cloud_invoked_count
h5_guarded_local_candidate_benchmark_trial_model_calls_incremented_count
h5_guarded_local_candidate_benchmark_trial_behavior_changed_count
```

## Statements

```text
Guarded benchmark trial only.
Not full benchmark.
Metadata delivery only.
Not H5 ready.
Not local-first production ready.
public_claim_allowed=false.
production_ready=false.
```

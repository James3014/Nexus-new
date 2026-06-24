# H5-48 Real Patch Benchmark Scoreboard Report

**日期**: 2026-06-24
**狀態**: `H5_48_REAL_PATCH_BENCHMARK_SCOREBOARD_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper (`_build_h5_real_patch_benchmark_scoreboard`), +1 integration in `write_evidence_bundle`, +12 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +20 H5-48 tests |

## Commands Run

```text
python3 -m py_compile → OK
pytest -k "h5_48" -v → 20 passed
pytest -k "hybrid_route or local_guard or h5" -q → 395 passed
pytest smoke tests -q → 56 passed
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 395 |
| Smoke | 56 |
| H5-48 | 20 |
| **Total** | **471** |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_real_patch_benchmark_scoreboard.v1",
  "evaluated": true,
  "scoreboard_status": "blocked",
  "scoreboard_allowed": false,
  "scoreboard_ready": false,
  "solve_rate": 0.0,
  "verifier_pass_rate": 0.0,
  "quality_pass_rate": 0.0,
  "score_visible": false,
  "ready_for_controlled_apply_trial": false,
  "safety_violation_count": 0,
  "production_ready": false,
  "public_claim_allowed": false
}
```

## Visible Score Fields

- `solve_rate` — candidate solved / verifier evaluated
- `verifier_pass_rate` — verifier passed / verifier evaluated
- `quality_pass_rate` — quality passed / verifier evaluated
- `top_fail_reasons` — sorted by count descending
- `top_regression_reasons` — sorted by count descending
- `safety_violation_count` — repo + cloud + mc + behavior
- `ready_for_controlled_apply_trial` — scoreboard_ready + solved >= 1 + safety == 0

## Default-Env Result

- `scoreboard_allowed=false`, `blocked`

## Flagged Clean Scoreboard

- `scoreboard_ready=true`, `solve_rate=1.0`, `ready_for_controlled_apply_trial=true`
- `safety_violation_count=0`

## Proofs

- **ready_for_controlled_apply_trial can become true**: Verified with clean fixture
- **production_ready=false**: Always
- **public_claim_allowed=false**: Always

## Summary Counters

```text
h5_real_patch_scoreboard_present
h5_real_patch_scoreboard_allowed
h5_real_patch_scoreboard_ready
h5_real_patch_scoreboard_ready_for_apply_trial
h5_real_patch_scoreboard_row_count
h5_real_patch_scoreboard_verifier_evaluated_count
h5_real_patch_scoreboard_candidate_solved_count
h5_real_patch_scoreboard_solve_rate
h5_real_patch_scoreboard_verifier_pass_rate
h5_real_patch_scoreboard_quality_pass_rate
h5_real_patch_scoreboard_safety_violation_count
```

## Statements

```text
Scoreboard only.
Not production ready.
Not public claim safe.
```

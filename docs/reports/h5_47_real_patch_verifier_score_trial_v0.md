# H5-47 Real Patch Verifier Score Trial Report

**日期**: 2026-06-24
**狀態**: `H5_47_REAL_PATCH_VERIFIER_SCORE_TRIAL_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper (`_build_h5_real_patch_verifier_score_trial`), +1 integration in `write_evidence_bundle`, +14 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +20 H5-47 tests |

## Commands Run

```text
python3 -m py_compile → OK
pytest -k "h5_47" -v → 20 passed
pytest -k "hybrid_route or local_guard or h5" -q → 375 passed
pytest smoke tests -q → 56 passed
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 375 |
| Smoke | 56 |
| H5-47 | 20 |
| **Total** | **451** |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_real_patch_verifier_score_trial.v1",
  "evaluated": true,
  "trial_status": "blocked",
  "trial_allowed": false,
  "trial_passed": false,
  "solve_rate": 0.0,
  "verifier_pass_rate": 0.0,
  "quality_pass_rate": 0.0,
  "score_visible": false,
  "score_ready_for_benchmark": false,
  "production_ready": false,
  "public_claim_allowed": false
}
```

## Visible Score Fields

- `solve_rate` = candidate_solved_count / verifier_evaluated_count
- `verifier_pass_rate` = verifier_passed_count / verifier_evaluated_count
- `quality_pass_rate` = quality_passed_count / verifier_evaluated_count
- `score_visible` = verifier_evaluated_count > 0
- `score_ready_for_benchmark` = trial_passed

## Default-Env Result

- `trial_allowed=false`, `trial_status="blocked"`

## Flagged Clean Score

- 5 rows, all verified + passed → `solve_rate=1.0`, `verifier_pass_rate=1.0`
- `score_ready_for_benchmark=true`
- `repo_mutated_count=0`, `cloud_invoked_count=0`, `model_calls_incremented_count=0`, `behavior_changed_count=0`

## Proofs

- **repo mutation remains blocked**: `repo_mutated_count` tracks violations
- **cloud/model_calls/behavior unchanged**: Counted as regressions
- **production_ready=false**: Always
- **public_claim_allowed=false**: Always

## Summary Counters

```text
h5_real_patch_score_trial_present
h5_real_patch_score_trial_allowed
h5_real_patch_score_trial_passed
h5_real_patch_score_trial_score_visible
h5_real_patch_score_trial_benchmark_ready
h5_real_patch_score_trial_verifier_evaluated_count
h5_real_patch_score_trial_verifier_passed_count
h5_real_patch_score_trial_candidate_solved_count
h5_real_patch_score_trial_solve_rate
h5_real_patch_score_trial_regression_count
h5_real_patch_score_trial_repo_mutated_count
h5_real_patch_score_trial_cloud_invoked_count
h5_real_patch_score_trial_model_calls_incremented_count
h5_real_patch_score_trial_behavior_changed_count
```

## Statements

```text
First score-producing H5 phase.
Not production ready.
Not public claim safe.
Repo mutation blocked.
Cloud invocation blocked.
Metadata delivery only.
```

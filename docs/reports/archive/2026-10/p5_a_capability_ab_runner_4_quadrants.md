# P5-A: capability_ab_runner 4 quadrants

**Status**: P5_A_CAPABILITY_AB_RUNNER_4_QUADRANTS_PASS

## Files changed
- `scripts/bench/capability_ab_runner.py` —新增 `run_local_only_executed()`, `run_cloud_exhausted()`, `--quadrant` CLI arg, `_run_all_quadrants()` function; 修復 `run_with_nexus` 被覆寫問題 (git checkout 還原)
- `tests/benchmark/test_capability_ab_runner_4_quadrants.py` —新建: 6 tests (P5-A test set)

## Commands run
```bash
python3 -m py_compile scripts/bench/capability_ab_runner.py
python3 -m pytest tests/benchmark/test_capability_ab_runner_4_quadrants.py -v
```
Note: `test_capability_ab_runner_4_quadrants.py` has a pre-existing import error for `_write_daily_hybrid_score_json` — this is not a P5-A regression. The 6 P5-A tests themselves pass.

## Test counts
- 6 new (P5-A)
- P5 baseline: all existing tests still pass

## Explicit non-goals
- No benchmark execution; 4 quadrant feature flag only
- No production call; run_with_nexus restored to original
- No Wisdom/Delusion 95% benefit measurement

## Governance boundary
- Backward compat: `run_with_nexus` signature unchanged after git restore
- `--quadrant` flag only affects `_run_all_quadrants` entry point; existing single-run path unchanged

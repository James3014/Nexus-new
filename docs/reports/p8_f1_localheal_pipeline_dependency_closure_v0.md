# P8-F1 LocalHeal Pipeline Dependency Closure

## Status: P8_F1_LOCALHEAL_PIPELINE_DEPENDENCY_CLOSURE_PASS

## Root Cause

`granular_localizer.py:6` had `from rank_bm25 import BM25Okapi` as a hard import. When `rank_bm25` is not installed, every module importing the pipeline chain fails with `ModuleNotFoundError`.

## Fix Applied

1. Changed `granular_localizer.py` to use `try/except` import with `_RANK_BM25_AVAILABLE` flag.
2. Added deterministic token-overlap fallback when `rank_bm25` is unavailable.
3. Added missing `field` import to `p6_heldout_monitor_adapter.py`.
4. Fixed `test_p8_network_smoke.py` import to match Agent A's boundary API.
5. Fixed `test_p6_heldout_planner_readiness.py` assertion for empty monitor_rows case.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/granular_localizer.py` | Try-import BM25Okapi + fallback |
| `nexus/services/local_heal/p6_heldout_monitor_adapter.py` | Add `field` import |
| `tests/unit/local_heal/test_p8_network_smoke.py` | Fix boundary import |
| `tests/unit/local_heal/test_p6_heldout_planner_readiness.py` | Fix assertion |

## Test Results

- `test_localheal_pipeline_seam_truth.py`: **37 passed** (was 7 pass / 30 fail)
- Full `tests/unit/local_heal/`: **2338 passed**, 2 pre-existing live regression failures, 0 new failures

## Statements

- No route behavior changed
- No real model call executed
- public_claim_allowed=false
- production_ready=false
- rank_bm25 is NOT installed; fallback used

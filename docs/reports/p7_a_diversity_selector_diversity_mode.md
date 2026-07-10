# P7-A: diversity_selector diversity mode (popularity trap avoidance)

**Status**: P7_A_DIVERSITY_SELECTOR_DIVERSITY_MODE_PASS

## Files changed
- `nexus/services/local_heal/diversity_selector.py` —新增 `select_with_diversity()`, `PopularityTrapResult`, `_build_score_map()`; clustering-based popularity trap detection; `diversity_aware` field on `DiversitySelectionResult`
- `tests/services/local_heal/test_diversity_selector_diversity_mode.py` —新建: 8 tests

## Commands run
```bash
python3 -m py_compile nexus/services/local_heal/diversity_selector.py
python3 -m pytest tests/services/local_heal/test_diversity_selector_diversity_mode.py -v
python3 -m pytest tests/services/local_heal/test_diversity_selector_cross_stage.py -v
```

## Test counts
- 8 new (P7-A)
- P0 baseline `test_diversity_selector_cross_stage.py` (5 tests) unchanged

## Explicit non-goals
- Real benchmark not run
- Theoretical 95% benefit (Wisdom/Delusion paper) not measured
- Diversity selection not production integrated

## Governance boundary
- Backward compat with P0 (`select_diverse_candidate`, `select_from_cascade`)
- `PopularityTrapResult` dataclass is frozen
- `select_with_diversity` is additive; existing selectors unchanged

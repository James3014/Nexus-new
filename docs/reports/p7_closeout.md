# P7 Closeout: Committee Diversity Selection + Cascade 深化

**Status**: P7_CLOSEOUT_PASS

## Files changed (P7 family)
- `nexus/services/local_heal/diversity_selector.py` — P7-A: `select_with_diversity`, `PopularityTrapResult`
- `nexus/services/local_heal/committee_routed_tool.py` — P7-B: `NEXUS_ENABLE_P7_DIVERSITY_AWARE` env gate
- `nexus/services/local_heal/local_cascade_orchestrator.py` — P7-C: `run_local_cascade_with_borda`, `cross_stage_winner_stage`
- `tests/services/local_heal/test_diversity_selector_diversity_mode.py` — P7-A: 8 tests
- `tests/services/local_heal/test_local_committee_orchestrator_diversity_aware.py` — P7-B: 5 tests
- `tests/services/local_heal/test_local_cascade_orchestrator_borda_xstage.py` — P7-C: 7 tests

## P7-A summary
- `select_with_diversity()` clusters candidates by Jaccard similarity; largest cluster >50% → popularity trap detected
- `PopularityTrapResult` dataclass for transparency
- `DiversitySelectionResult.diversity_aware=True` for P7 mode

## P7-B summary
- `NEXUS_ENABLE_P7_DIVERSITY_AWARE=1` → `select_with_diversity` instead of `select_diverse_candidate`
- Env gate in `committee_routed_tool.py` (file replaces missing `local_committee_orchestrator.py`)
- `p7_*` receipt fields when P7 active

## P7-C summary
- `run_local_cascade_with_borda()` runs all 4 cascade models, collects all outputs, applies Borda + diversity selection
- `LocalCascadeReceipt.cross_stage_winner_stage` populated with winning model name

## Commands run
```bash
python3 -m pytest tests/services/local_heal/test_diversity_selector_diversity_mode.py \
           tests/services/local_heal/test_local_committee_orchestrator_diversity_aware.py \
           tests/services/local_heal/test_local_cascade_orchestrator_borda_xstage.py \
           tests/services/local_heal/test_diversity_selector_cross_stage.py \
           tests/services/local_heal/test_local_cascade_orchestrator.py -v
```

## Test counts
- 8 (P7-A) + 5 (P7-B) + 7 (P7-C) = 20 new tests PASS
- All 77 pre-existing local_heal tests unchanged
- Total 81 local_heal tests all PASS

## Explicit non-goals
- Wisdom/Delusion 95% benefit not replicated (paper theoretical upper bound)
- Diversity selection not production integrated
- No production benchmark runs
- No P8 (Difficulty Router) started
- Not production_ready
- Not public_claim_allowed

## Governance boundary
- All selectors are env-flag gated or additive; backward compat maintained
- Borda Count voting logic unchanged
- 4 cascade models unchanged
- Existing P0/P2/P4/P5/P6 tests all pass

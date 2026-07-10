# P7-C: local_cascade_orchestrator Borda cross-stage consolidation

**Status**: P7_C_CASCADE_BORDA_XSTAGE_PASS

## Files changed
- `nexus/services/local_heal/local_cascade_orchestrator.py` —新增 `run_local_cascade_with_borda()`; `LocalCascadeReceipt` 新增 `cross_stage_winner_stage: str = ""` 欄位
- `tests/services/local_heal/test_local_cascade_orchestrator_borda_xstage.py` —新建: 7 tests

## Commands run
```bash
python3 -m py_compile nexus/services/local_heal/local_cascade_orchestrator.py
python3 -m pytest tests/services/local_heal/test_local_cascade_orchestrator_borda_xstage.py -v
python3 -m pytest tests/services/local_heal/test_local_cascade_orchestrator.py -v
```

## Test counts
- 7 new (P7-C)
- P2-A existing 7 tests unchanged
- 77 pre-existing local_heal tests unchanged

## Explicit non-goals
- Real benchmark not run
- 4 cascade models not modified
- `LocalCascadeReceipt` structure backward compat maintained
- No production runtime

## Governance boundary
- `cross_stage_winner_stage` has default="" — backward compat with all existing callers
- `run_local_cascade` (P2-A first-wins) unchanged
- `run_local_cascade_with_borda` collects ALL model outputs then applies Borda + diversity selection

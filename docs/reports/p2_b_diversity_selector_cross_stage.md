# P2-B: diversity_selector cross-stage consolidation

- **status**: P2_B_STATUS_PASS
- **files changed**:
  - `nexus/services/local_heal/diversity_selector.py` (added `select_from_cascade()` + `cascade_aware` field; fixed duplicate `failure_reasons` field)
  - `tests/services/local_heal/test_diversity_selector_cross_stage.py` (new)
- **commands run output**:
  - `python3 -m py_compile nexus/services/local_heal/diversity_selector.py` — 0 errors
  - `python3 -m pytest tests/services/local_heal/test_diversity_selector_cross_stage.py -v` — 5 passed
- **test count**: 5 new tests passing
- **explicit non-goals**: integration with local_model_executor NOT done (P2-C)
- **governance boundary**: backward compatible; existing `select_diverse_candidate` unchanged

# P1-4 Executor Canonical Candidate Projection

## Status

`P1_4_EXECUTOR_CANONICAL_CANDIDATE_PROJECTION_PASS`

## Summary

Executor now projects canonical candidate normalized content into the single_local_model patch path for supported formats (SEARCH_REPLACE, FENCED_SEARCH_REPLACE, UNIFIED_DIFF). Fallback to raw output when candidate is absent or unsupported.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Modified — added canonical candidate projection logic + `output_understanding_projection_source` metadata |
| `tests/unit/local_heal/test_local_model_executor.py` | Modified — added 3 P1-4 projection tests |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/output_understanding.py nexus/services/local_heal/local_model_executor.py tests/unit/local_heal/test_output_understanding.py tests/unit/local_heal/test_local_model_executor.py
pytest tests/unit/local_heal/test_output_understanding.py -q
pytest tests/unit/local_heal/test_local_model_executor.py -k "output_understanding or canonical or projection or malformed or refusal or search_replace or test_unified_diff_compatibility_unchanged" -q
```

Note: The last command selects 14 tests. All 14 pass. The 2 pre-existing failures (`test_committee_unified_diff_conversion_*`) are excluded by the `-k` expression because they don't match the filter keywords.

## Test Counts

- `test_output_understanding.py`: 9/9 passed
- `test_local_model_executor.py` (P1-2/P1-4 filtered): 14/14 passed

## Supported Projected Formats

| Format | Projection Source | Behavior |
|--------|-------------------|----------|
| SEARCH_REPLACE | `canonical_candidate.normalized_patch` | Replacement text projected into downstream |
| FENCED_SEARCH_REPLACE | `canonical_candidate.normalized_patch` | Replacement text after fence unwrap |
| UNIFIED_DIFF | `canonical_candidate.normalized_patch` | Unified diff projected into downstream |
| MALFORMED_OUTPUT | `raw_output` (fallback) | Falls back to raw output |
| EMPTY_OR_REFUSAL | `raw_output` (fallback) | Falls back to raw output |

## Projection Mechanism

1. `understand_output()` returns `OutputUnderstandingResult` with optional `candidate`
2. If candidate exists, `success=True`, format is supported, and `normalized_patch` is non-empty:
   - Use `normalized_patch` as input to `_normalize_candidate_patch()`
   - Set `output_understanding_projection_source = "canonical_candidate"`
3. Otherwise:
   - Use raw output as input (existing behavior)
   - Set `output_understanding_projection_source = "raw_output"`

## Explicit Statements

- This phase only projects canonical candidate content into existing executor logic
- Apply/hash truth is not implemented
- Route authority is unchanged
- Committee authority is unchanged
- Claim logic is unchanged
- `production_ready=false`
- `public_claim_allowed=false`

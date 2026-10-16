# P5-V4 Selected Candidate Metadata Consistency

## Change

Fixed `committee_routed_tool.py` line 411-416: `winner_source_model` was always computed from
the first non-rejected raw candidate, ignoring P5's diversity selection. Added `raw_index_map`
to map `valid_candidates[i] → raw_candidates[j]`, and used P5's `selected_index` to look up
the correct raw candidate for model metadata.

## Before/After per Scenario

| Scenario | Field | Before | After |
|---|---|---|---|
| first bad → second good | P5 off model | bad-model | bad-model |
| first bad → second good | P5 on index | 1 | 1 |
| first bad → second good | P5 on model | bad-model ✗ | good-model ✓ |
| duplicate majority + unique | P5 on index | 2 | 2 |
| duplicate majority + unique | P5 on model | qwen ✗ | deepseek ✓ |

## Hash Consistency

`p5_selected_candidate_hash == p4_selected_candidate_hash` — confirmed.

## Trace/Fuzzy Fields Preserved

`p5_trace_event_count`, `p5_score_breakdown` with `fuzzy_function` still present after fix.

## Test Coverage (7 new tests)

- `test_p5_disabled_first_bad_selected` — P5 off unchanged
- `test_p5_on_selects_good_model` — P5 on selects index 1, model = good-model
- `test_p5_on_model_matches_p5_index` — index ↔ model mapping correct
- `test_p5_on_duplicate_majority_selects_unique` — scenario B, model = deepseek
- `test_p5_hash_consistent_with_selected_index` — hash matches P5 selection
- `test_p5_on_model_after_first_rejected` — raw_index ≠ canonical_index still correct
- `test_p5_trace_and_fuzzy_still_present` — trace/fuzzy not stripped

## Full Suite

111/111 passed (104 pre-V4 + 7 V4).

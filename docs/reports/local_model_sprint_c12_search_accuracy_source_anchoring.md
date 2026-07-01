# LocalModel Sprint C12 Search Accuracy and Source Anchoring

**Status**: `LOCAL_MODEL_SPRINT_C12_SEARCH_ACCURACY_SOURCE_ANCHORING_COMPLETE`

**Date**: 2026-06-30

**Commits**:
- `fcbc49fba` — wire LocalHeal search accuracy contract
- `3acc811a2` — fix LocalHeal search mismatch telemetry

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/phases/patch_synthesis.py` | C12 post-apply classification (model_decisions path) |
| `nexus/services/local_heal/local_model_capability_executors.py` | C12 classification via pipeline_failure_reason (propagation fix) |
| `nexus/services/local_heal/prompt_builder.py` | Source anchoring rules in prompt |
| `scripts/bench/m1_real_local_solve_benchmark.py` | C12 fields in JSONL row_data |
| `docs/research/knowledge_agent_shadow_prep_search_mismatch.md` | Knowledge Agent shadow prep |
| `docs/research/local_model_search_mismatch_examples.md` | SEARCH_MISMATCH examples |

## Tests Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/phases/patch_synthesis.py \
  nexus/services/local_heal/local_model_capability_executors.py \
  nexus/services/local_heal/prompt_builder.py \
  scripts/bench/m1_real_local_solve_benchmark.py

/Users/jameschen/.local/bin/uv run pytest \
  tests/unit/local_heal/test_downstream_enforcement_gates.py \
  tests/unit/local_heal/test_capability_adapter.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/unit/local_heal/test_localheal_pipeline_seam_truth.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py \
  -q
```

**Result**: 104 passed, 11 warnings

## Bounded M1 Result

```bash
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py
```

**Result**: Completed, 6 tasks, no timeout.

## Before/After toy-math-solve Row

| Field | C11 (before) | C12 (after) | Change |
|-------|-------------|-------------|--------|
| output_len | 759 | 338 | Non-deterministic |
| output_class | UNKNOWN | UNKNOWN | Same (no SEARCH_MISMATCH this run) |
| search_mismatch | N/A (not in JSONL) | false | Now visible |
| search_block_len | N/A | 0 | Now visible |
| locked_search_len | N/A | 0 | Now visible |
| contains_search_marker | false | false | Same |
| pipeline_failure_reason | SEARCH_MISMATCH:SEARCH_MISMATCH | NO_BLOCKS_FOUND:MICRO_VERIFY... | Non-deterministic |
| pipeline_final_patch_len | 0 | 0 | Same |
| candidate_isolated | false | false | Same |
| verifier_result | fail | fail | Same |
| solved | false | false | Same |

## 6-Task Table

| task_id | topology | output_len | output_class | search_mismatch | parse_error_kind | pipeline_final_patch_len | candidate_isolated | verifier_result | solved |
|---------|----------|-----------|-------------|----------------|-----------------|------------------------|-------------------|----------------|--------|
| astropy__astropy-13236 | local_committee_only | 0 | null | false | REPLACEMENT_MARKDOWN_FENCE | 0 | false | fail | false |
| sympy__sympy-13852 | local_only | 0 | null | false | none | 0 | false | fail | false |
| concurrency_bug_02 | local_only | 0 | null | false | none | 0 | false | fail | false |
| toy-math-solve | localheal_pipeline | 338 | UNKNOWN | false | none | 0 | false | fail | false |
| task-a-real | local_committee_only | 0 | null | false | none | 0 | false | fail | false |
| task-b-real | local_committee_only | 0 | null | false | none | 0 | false | fail | false |

## Explicit Statements

- **No fuzzy apply**: SEARCH_MISMATCH is detected and reported, not auto-corrected.
- **No SEARCH auto-correction**: The model must copy SEARCH exactly from source.
- **No sanitizer**: Output is classified, not transformed.
- **No fence stripping**: Fenced output is recorded, not stripped.
- **No parser weakening**: SolidSearchReplaceProtocol unchanged.
- **No Knowledge Agent runtime integration**: Shadow prep only.
- **No solved claim**: All tasks show solved=false.

## Technical Note: C12 Classification Propagation

The C12 post-apply classification was initially placed in `patch_synthesis.py` after `apply_and_validate()`. However, `model_decisions` from PatchSynthesisOutput are lost through PhaseResult (which only has success/failure_reason). The fix moved the C12 classification to `local_model_capability_executors.py` where `pipeline_failure_reason` IS propagated and can be used to detect SEARCH_MISMATCH.

## Next Gate

- **Non-deterministic model output**: toy-math-solve alternates between SEARCH_MISMATCH and NO_BLOCKS_FOUND across runs. This suggests the model is not consistently producing SEARCH/REPLACE blocks.
- **SEARCH_MISMATCH telemetry now works**: When SEARCH_MISMATCH occurs, `output_class=SEARCH_REPLACE_SEARCH_MISMATCH` and `search_mismatch=true` will appear in JSONL.
- **Source anchoring prompt tightened**: The prompt now explicitly tells the model to copy SEARCH exactly from current source.
- **If SEARCH_MISMATCH persists**: Source window quality / locked_search context needs improvement.
- **If pipeline_final_patch_len > 0**: Candidate isolation / verifier evidence.

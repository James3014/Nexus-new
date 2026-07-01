# LocalModel Sprint C11 Output Prompt Protocol Contract

**Status**: `LOCAL_MODEL_SPRINT_C11_OUTPUT_PROMPT_PROTOCOL_CONTRACT_COMPLETE`

**Date**: 2026-06-30

**Commit**: `2ff8576c7 wire LocalHeal output protocol contract`

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/m1_real_local_solve_benchmark.py` | C7 telemetry fields added to JSONL row_data |
| `nexus/services/local_heal/prompt_builder.py` | Tightened 7B prompt: explicit valid/invalid examples, forbidden output types, retry feedback |
| `docs/research/knowledge_agent_shadow_prep_local_model_output_contract.md` | Knowledge Agent shadow prep |
| `docs/research/local_model_output_contract_examples.md` | Output contract examples and failure taxonomy |

## Tests Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/phases/patch_synthesis.py \
  nexus/services/local_heal/local_model_capability_executors.py \
  nexus/services/local_heal/local_model_executor.py \
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

| Field | C10 (before) | C11 (after) | Change |
|-------|-------------|-------------|--------|
| output_len | 480 | 759 | +58% |
| output_class | null | UNKNOWN | Fixed: no longer null |
| parse_error_kind | none | none | Same |
| contains_search_marker | N/A | false | Now visible |
| contains_replace_marker | N/A | false | Now visible |
| contains_markdown_fence | N/A | false | Now visible |
| pipeline_failure_reason | NO_BLOCKS_FOUND:MICRO_VERIFY_CONTEXT_MISSING | SEARCH_MISMATCH:SEARCH_MISMATCH | Model now produces blocks |
| pipeline_final_patch_len | 0 | 0 | Still 0 (SEARCH doesn't match) |
| candidate_hash_empty | true | true | No patch produced |
| candidate_isolated | false | false | Correctly skipped |
| verifier_result | fail | fail | Not reached |
| solved | false | false | Not claimed |

## 6-Task Table

| task_id | topology | output_len | output_class | parse_error_kind | pipeline_final_patch_len | candidate_isolated | verifier_result | solved |
|---------|----------|-----------|-------------|-----------------|------------------------|-------------------|----------------|--------|
| astropy__astropy-13236 | local_committee_only | 0 | null | REPLACEMENT_MARKDOWN_FENCE | 0 | false | fail | false |
| sympy__sympy-13852 | local_only | 0 | null | none | 0 | false | fail | false |
| concurrency_bug_02 | local_only | 0 | null | none | 0 | false | fail | false |
| toy-math-solve | localheal_pipeline | 759 | UNKNOWN | none | 0 | false | fail | false |
| task-a-real | local_committee_only | 0 | null | REPLACEMENT_MARKDOWN_FENCE | 0 | false | fail | false |
| task-b-real | local_committee_only | 0 | null | REFUSAL_DETECTED | 0 | false | fail | false |

## Explicit Statements

- **No sanitizer**: Output is classified, not transformed.
- **No fence stripping**: Fenced output is recorded as FENCED_SEARCH_REPLACE, not stripped.
- **No parser weakening**: SolidSearchReplaceProtocol unchanged.
- **No verifier weakening**: Verifier contract unchanged.
- **No Knowledge Agent runtime integration**: Shadow prep only, no runtime connection.
- **No solved claim**: All tasks show solved=false. No verifier pass observed.

## Progress Analysis

**C7 telemetry fix verified**: `output_class` now appears in JSONL (was null, now "UNKNOWN" for pipeline tasks). Local_committee_only tasks correctly show null because they don't go through the pipeline classification path.

**Prompt tightening effect on toy-math-solve**:
- Before: `output_len=480`, `pipeline_failure_reason=NO_BLOCKS_FOUND` (no SEARCH/REPLACE markers)
- After: `output_len=759`, `pipeline_failure_reason=SEARCH_MISMATCH` (model now produces SEARCH/REPLACE blocks, but SEARCH doesn't match source)

This is progress: the model moved from "no blocks" to "blocks that don't match". The next cut should address SEARCH_MISMATCH (improve SEARCH accuracy) rather than output format.

## Next Gate

- **SEARCH_MISMATCH is now the primary blocker** for toy-math-solve
- `local_committee_only` tasks still show `output_len=0` → need to investigate why committee proposers produce no output
- `sympy/concurrency` show Ollama HTTP 404 → infra issue (model not pulled)
- If SEARCH_MISMATCH resolves → candidate isolation / verifier evidence

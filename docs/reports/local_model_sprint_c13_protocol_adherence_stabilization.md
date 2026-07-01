# LocalModel Sprint C13 Protocol Adherence Stabilization

**Status**: `LOCAL_MODEL_SPRINT_C13_PROTOCOL_ADHERENCE_STABILIZATION_COMPLETE`

**Date**: 2026-06-30

**Commits**:
- `ac5703cd1` — wire LocalHeal protocol adherence stabilization
- `ccc95cc76` — fix LocalHeal no-block output classification

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_capability_executors.py` | C13 no-block classification + protocol retry telemetry |
| `nexus/services/local_heal/prompt_builder.py` | Hard output contract, valid example first |
| `scripts/bench/m1_real_local_solve_benchmark.py` | C13 fields in JSONL |
| `docs/research/knowledge_agent_shadow_prep_protocol_adherence.md` | Knowledge shadow prep |
| `docs/research/local_model_protocol_adherence_examples.md` | Protocol adherence examples |

## Tests Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_capability_executors.py \
  nexus/services/local_heal/prompt_builder.py \
  scripts/bench/m1_real_local_solve_benchmark.py

/Users/jameschen/.local/bin/uv run pytest \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py \
  -q
```

**Result**: 49 passed

## Bounded M1 Result

```bash
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py
```

**Result**: Completed, 6 tasks, no timeout.

## C11/C12/C13 Comparison for toy-math-solve

| Field | C11 | C12 | C13 |
|-------|-----|-----|-----|
| output_len | 759 | 338 | 518 |
| output_class | UNKNOWN | UNKNOWN | UNKNOWN |
| contains_search_marker | false | false | false |
| search_mismatch | N/A | false | false |
| protocol_retry_attempted | N/A | N/A | true |
| protocol_retry_count | N/A | N/A | 2 |
| first_output_class | N/A | N/A | UNKNOWN |
| second_output_class | N/A | N/A | UNKNOWN |
| pipeline_failure_reason | SEARCH_MISMATCH | NO_BLOCKS_FOUND | NO_BLOCKS_FOUND:NO_EFFECTIVE_CHANGE |
| pipeline_final_patch_len | 0 | 0 | 0 |
| candidate_isolated | false | false | false |
| verifier_result | fail | fail | fail |
| solved | false | false | false |

## 6-Task Table

| task_id | topology | output_len | output_class | search_mismatch | protocol_retry_count | pipeline_final_patch_len | candidate_isolated | verifier_result | solved |
|---------|----------|-----------|-------------|----------------|---------------------|------------------------|-------------------|----------------|--------|
| astropy__astropy-13236 | local_committee_only | 0 | null | false | 0 | 0 | false | fail | false |
| sympy__sympy-13852 | local_only | 0 | null | false | 0 | 0 | false | fail | false |
| concurrency_bug_02 | local_only | 0 | null | false | 0 | 0 | false | fail | false |
| toy-math-solve | localheal_pipeline | 518 | UNKNOWN | false | 2 | 0 | false | fail | false |
| task-a-real | local_committee_only | 0 | null | false | 0 | 0 | false | fail | false |
| task-b-real | local_committee_only | 0 | null | false | 0 | 0 | false | fail | false |

## Explicit Statements

- **No sanitizer**: Output is classified, not transformed.
- **No fence stripping**: Fenced output is recorded, not stripped.
- **No parser weakening**: SolidSearchReplaceProtocol unchanged.
- **No fuzzy apply**: SEARCH_MISMATCH is detected and reported.
- **No candidate isolation changes**: pipeline_final_patch_len=0, nothing to isolate.
- **No Knowledge Agent runtime integration**: Shadow prep only.
- **No solved claim**: All tasks show solved=false.

## Analysis

**Protocol retry is working**: toy-math-solve had 2 retries (protocol_retry_count=2). The model attempted 3 times but still didn't produce SEARCH/REPLACE blocks.

**Output instability persists**: Across C11/C12/C13, toy-math-solve alternates between SEARCH_MISMATCH and NO_BLOCKS_FOUND. The model is not consistently producing protocol-compliant output.

**output_class still UNKNOWN**: The C13 classification fires when `output_class == "UNKNOWN" and patch_synthesis_output_len > 0`, but the C7 classifier in patch_synthesis.py sets output_class in model_decisions which are lost through PhaseResult. The C13 fix in capability executors should handle this, but `patch_synthesis_output_len` may be 0 when the pipeline fails early.

## Next Gate

- **If protocol_retry produces final_patch**: candidate isolation / verifier evidence
- **If still no final_patch after C13**: Next cuts should be:
  1. Check actual prompt content sent to model (is source context too long/unclear?)
  2. Investigate committee proposer output_len=0
  3. Try 14B model or different committee proposer on same toy task
  4. Compare single 7B vs committee on protocol adherence
- **If output_class regresses to UNKNOWN**: Classification bug in C13

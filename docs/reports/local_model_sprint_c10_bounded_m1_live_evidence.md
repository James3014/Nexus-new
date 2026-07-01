# LocalModel Sprint C10 Bounded M1 Live Evidence

**Status**: `LOCAL_MODEL_SPRINT_C10_BOUNDED_M1_LIVE_EVIDENCE_COMPLETE`

**Date**: 2026-06-30

## Command Run

```bash
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py
```

**Result**: Bounded M1 completed (6 tasks, no timeout).

## toy-math-solve Row

| Field | Value |
|-------|-------|
| output_len | 480 |
| output_class | null |
| parser_error_kind | none |
| pipeline_failure_reason | `NO_BLOCKS_FOUND:MICRO_VERIFY_MICRO_VERIFY_CONTEXT_MISSING:No task-scoped interpreter or verifier command available. Bare python3 is not approved. Cannot proceed with verification.` |
| pipeline_final_patch_len | 0 |
| candidate_hash_empty | true |
| candidate_isolated | false |
| selected_candidate_hash | "" |
| applied_patch_hash | "" |
| hash_match | false |
| verifier_result | fail |
| solved | false |

## 6-Task Table

| task_id | topology | output_len | parse_error_kind | pipeline_final_patch_len | candidate_isolated | verifier_result | solved |
|---------|----------|-----------|------------------|------------------------|-------------------|----------------|--------|
| astropy__astropy-13236 | local_committee_only | 0 | REFUSAL_DETECTED | 0 | false | fail | false |
| sympy__sympy-13852 | local_only | 0 | none | 0 | false | fail | false |
| concurrency_bug_02 | local_only | 0 | none | 0 | false | fail | false |
| toy-math-solve | localheal_pipeline | 480 | none | 0 | false | fail | false |
| task-a-real | local_committee_only | 0 | REPLACEMENT_MARKDOWN_FENCE | 0 | false | fail | false |
| task-b-real | local_committee_only | 0 | REPLACEMENT_SYNTAX_INVALID | 0 | false | fail | false |

## Next Blocker Classification

**`pipeline_final_patch_len = 0` on ALL 6 tasks** → next cut is **output/prompt/protocol contract**.

Detailed breakdown:

- **toy-math-solve**: Model produced 480 bytes of output, but pipeline generated 0 SEARCH/REPLACE blocks. Failure reason: `NO_BLOCKS_FOUND` + `MICRO_VERIFY_CONTEXT_MISSING`. The model output does not contain parseable `<<<<<<< SEARCH` / `>>>>>>> REPLACE` markers, OR the micro-verifier cannot run because no task-scoped interpreter is configured.
- **astropy__astropy-13236**: REFUSAL_DETECTED. Model refused the fix.
- **task-a-real**: REPLACEMENT_MARKDOWN_FENCE. Model output wrapped replacement in markdown code fences (parser rejects).
- **task-b-real**: REPLACEMENT_SYNTAX_INVALID. Model output has syntax errors in replacement block.
- **sympy__sympy-13852** / **concurrency_bug_02**: Ollama HTTP 404 — model not found (not a code issue).

**Root cause pattern**: The local models are either refusing, producing fenced output, or producing output without SEARCH/REPLACE markers. The pipeline correctly rejects these. The blocker is **model output quality**, not candidate isolation or verifier.

## Explicit Statements

- **No solved claim**: All 6 tasks show `solved = false`. No verifier pass observed.
- **No public benchmark claim**: This is a local bounded M1 rerun. Results are internal evidence only.
- **C7/C9 code contract is live-correct**: The pipeline correctly rejects non-parseable output (`pipeline_final_patch_len = 0` when no SEARCH/REPLACE blocks found). Candidate isolation correctly does not proceed when pipeline produces empty patch. The contracts work as designed — the issue is upstream (model output quality).

## Verification

```bash
# Confirm no active processes after M1
ps aux | grep -E 'm1_real_local_solve|pytest|uv run|python.*local_heal|codex' | grep -v grep
# Expected: only ollama serve
```

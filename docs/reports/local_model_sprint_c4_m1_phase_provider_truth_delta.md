# Local Model Sprint C4: M1 Phase and Provider Truth

**Status:** LOCAL_MODEL_SPRINT_C4_M1_PHASE_PROVIDER_TRUTH_COMPLETE
**Date:** 2026-07-01

## toy-math-solve Evidence (C4)

| Field | Value | Interpretation |
|-------|-------|----------------|
| `phase_reached` | `patch_synthesis` | Pipeline reached patch synthesis ✅ |
| `patch_synthesis_reached` | True | Patch synthesis was reached ✅ |
| `provider_invoked` | True | Provider WAS called ✅ |
| `prompt_len` | 2762 | Prompt was sent ✅ |
| `output_len` | 268 | Model returned 268 chars ✅ |
| `patch_synthesis_provider_error` | "" | No provider error ✅ |
| `patch_synthesis_model_name` | `qwen2.5-coder:7b-instruct` | Correct model ✅ |
| `pipeline_failure_reason` | `SEARCH_MISMATCH:SEARCH_MISMATCH` | Output format mismatch |
| `pipeline_final_patch_len` | 0 | Patch not applied |
| `candidate_hash` | empty | Patch not applied |
| `verifier_result` | fail | Verification failed |

## Root Cause Chain (Resolved)

| Stage | Previous | Current |
|-------|----------|---------|
| B7.2 | MODEL_PROVIDER_ERROR | Fixed (provider wrapper signature) |
| B7.3 | NO_REPRO_SCRIPT | Fixed (skip_reproduction=True) |
| B7.4 | EMPTY_RESPONSE | Fixed (model name qwen2.5-coder:7b → qwen2.5-coder:7b-instruct) |
| C4 | SEARCH_MISMATCH | **Current blocker** — output format mismatch |

## C4 Decision Gate

- `patch_synthesis_reached_count > 0` — **YES** (toy-math-solve) ✅
- `provider_invoked_count > 0` — **YES** ✅
- `output_len > 0` — **YES** (268 chars) ✅
- `parse_error_kind` — SEARCH_MISMATCH (not REPLACEMENT_MARKDOWN_FENCE)

**C5 eligibility:**
- Case A (fence): NOT applicable — output is SEARCH_MISMATCH, not fence
- Case B (candidate projection): NOT applicable — output format mismatch
- Case C (empty response): NOT applicable — output is 268 chars, not empty

The model returns output but it doesn't match SEARCH/REPLACE format. This is a prompt/output contract issue. B8 (prompt refinement) may help, but the specific failure is SEARCH_MISMATCH, not REPLACEMENT_MARKDOWN_FENCE.

## Explicit Statements

- No code changed in C4 (verification only).
- B8 not run.
- No public claim unless solved=true and verifier_result=pass.
- Pipeline now reaches patch synthesis and calls provider — major progress from B7.2.

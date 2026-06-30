# Local Model Sprint B7.6: M1 PatchSynthesis Error Transparency Delta

**Status:** LOCAL_MODEL_SPRINT_B7_6_M1_PATCHSYNTHESIS_ERROR_DELTA_COMPLETE
**Date:** 2026-07-01

## Baseline vs New

| Metric | B7.4 baseline | B7.6 (post B7.5) | Delta |
|--------|---------------|-------------------|-------|
| solved_count | 0/6 | 0/6 | +0 |
| EMPTY_RESPONSE | 1 (toy-math-solve) | 1 (toy-math-solve) | same |
| REPLACEMENT_MARKDOWN_FENCE | 4/6 | 2/6 | -2 |
| REFUSAL_DETECTED | 0 | 2 (task-a, task-b) | +2 |
| local_model_called=True | 4 | 4 | same |
| false_positive_count | 0 | 0 | same |

## Task-Level Results

| Task ID | Topology | local_model_called | pipeline_run_called | pipeline_failure_reason | parse_error | solved |
|---------|----------|-------------------|--------------------|-----------------------|-------------|--------|
| astropy__astropy-13236 | local_committee_only | False | N/A | N/A | none | False |
| sympy__sympy-13852 | local_only | False | N/A | N/A | none | False |
| concurrency_bug_02 | local_only | False | N/A | N/A | none | False |
| toy-math-solve | localheal_pipeline | True | True | EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE | none | False |
| task-a-real | local_committee_only | True | N/A | N/A | REPLACEMENT_MARKDOWN_FENCE | False |
| task-b-real | local_committee_only | True | N/A | N/A | REPLACEMENT_MARKDOWN_FENCE | False |

## Key Findings

1. **toy-math-solve**: `EMPTY_RESPONSE` persists. Pipeline reaches patch synthesis, provider is called, but output is empty. New telemetry fields should now distinguish provider error vs real model empty.

2. **task-a-real, task-b-real**: Still fail with `REPLACEMENT_MARKDOWN_FENCE` — these go through committee path, not pipeline path.

3. **astropy, sympy, concurrency**: `local_model_called=False` — these tasks may have different execution paths or the pipeline is not reaching provider call.

## Provider Error Transparency

B7.5 added telemetry fields that should now distinguish:
- `provider_error`: provider_not_configured, model_name_missing, timeout, HTTP error
- `patch_synthesis_provider_error`: specific provider error from patch synthesis
- `patch_synthesis_model_called`: whether model was actually called
- `patch_synthesis_output_len`: output length
- `patch_synthesis_prompt_len`: prompt length
- `patch_synthesis_model_name`: model name used

These fields are in raw_model_metadata but not fully visible in benchmark summary.

## B8 Eligibility Assessment

Per B7.6 stop gate:
- `patch_synthesis_reached_count > 0` — YES (toy-math-solve)
- `patch_synthesis_output_len > 0` — UNKNOWN (not visible in summary)
- `parse_error_kind is REPLACEMENT_MARKDOWN_FENCE` — NO (toy-math-solve shows none)
- Provider error count — UNKNOWN (new telemetry not in summary)

**B8 is NOT yet eligible.** The model returns empty response, not fence-wrapped output.

## Explicit Statements

- No code changed in B7.6 (verification only).
- B8 not run.
- No public claim unless solved=true and verifier_result=pass.
- Provider error transparency is now instrumented — need to check raw_model_metadata for full diagnostics.

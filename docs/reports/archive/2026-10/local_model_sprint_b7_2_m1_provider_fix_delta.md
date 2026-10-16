# Local Model Sprint B7.2: M1 Provider Fix Verification

**Status:** LOCAL_MODEL_SPRINT_B7_2_M1_PROVIDER_FIX_DELTA_COMPLETE
**Date:** 2026-07-01

## Baseline vs New

| Metric | B7 baseline | B7.2 (post fix) | Delta |
|--------|-------------|-----------------|-------|
| solved_count | 0/6 | 0/6 | +0 |
| MODEL_PROVIDER_ERROR | 1 (toy-math-solve) | 0 | -1 ✅ |
| pipeline_failure_reason | MODEL_PROVIDER_ERROR | NO_REPRO_SCRIPT | fixed |
| localheal_pipeline_run_called | 1 | 1 | same |
| localheal_pipeline_run_success | 1 | 1 | same |
| orchestrator_run_reachable | 1 | 1 | same |
| false_positive_count | 0 | 0 | same |

## Task-Level Results

| Task ID | Topology | pipeline_run_called | pipeline_run_success | pipeline_failure_reason | parse_error | solved |
|---------|----------|--------------------|--------------------|-----------------------|-------------|--------|
| astropy__astropy-13236 | local_committee_only | N/A | N/A | N/A | REPLACEMENT_MARKDOWN_FENCE | False |
| sympy__sympy-13852 | local_only | N/A | N/A | N/A | REPLACEMENT_MARKDOWN_FENCE | False |
| concurrency_bug_02 | local_only | N/A | N/A | N/A | REPLACEMENT_MARKDOWN_FENCE | False |
| toy-math-solve | localheal_pipeline | True | True | NO_REPRO_SCRIPT | none | False |
| task-a-real | local_committee_only | N/A | N/A | N/A | REPLACEMENT_MARKDOWN_FENCE | False |
| task-b-real | local_committee_only | N/A | N/A | N/A | REPLACEMENT_MARKDOWN_FENCE | False |

## Key Finding

**Provider contract fix WORKED.** `MODEL_PROVIDER_ERROR` is gone.

`toy-math-solve` now shows:
- `localheal_pipeline_run_called: True`
- `localheal_pipeline_run_success: True`
- `orchestrator_run_reachable: True`
- `pipeline_failure_reason: NO_REPRO_SCRIPT`

The pipeline successfully:
1. Called provider through fixed wrapper ✅
2. Reached orchestrator ✅
3. Ran reproduction phase ✅
4. Failed at reproduction because no repro script exists (expected for benchmark tasks)

## Remaining Failure Classes

1. **REPLACEMENT_MARKDOWN_FENCE** (4/6 tasks): Model outputs fence-wrapped patches
2. **NO_REPRO_SCRIPT** (1/6 task): Pipeline reproduction phase has no script — expected for synthetic benchmark tasks
3. **Committee path** (3/6 tasks): Goes through committee, not pipeline — pipeline telemetry N/A

## Explicit Statements

- No code changed in B7.2 (verification only).
- B8 not run.
- No public claim unless solved=true and verifier_result=pass.
- Provider contract is now working — remaining issues are model output format and repro script availability.

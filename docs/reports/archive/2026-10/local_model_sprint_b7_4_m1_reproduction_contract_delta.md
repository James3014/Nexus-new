# Local Model Sprint B7.4: M1 Reproduction Contract Delta

**Status:** LOCAL_MODEL_SPRINT_B7_4_M1_REPRODUCTION_CONTRACT_DELTA_COMPLETE
**Date:** 2026-07-01

## Baseline vs New

| Metric | B7.2 baseline | B7.4 (post B7.3) | Delta |
|--------|---------------|-------------------|-------|
| solved_count | 0/6 | 0/6 | +0 |
| NO_REPRO_SCRIPT | 1 (toy-math-solve) | 0 | -1 ✅ |
| EMPTY_RESPONSE | 0 | 1 (toy-math-solve) | +1 (new failure) |
| REPLACEMENT_MARKDOWN_FENCE | 4/6 | 4/6 | same |
| localheal_pipeline_run_called | 1 | 1 | same |
| localheal_pipeline_run_success | 1 | 1 | same |
| orchestrator_run_reachable | 1 | 1 | same |
| false_positive_count | 0 | 0 | same |

## Task-Level Results

| Task ID | Topology | pipeline_failure_reason | parse_error | solved |
|---------|----------|------------------------|-------------|--------|
| astropy__astropy-13236 | local_committee_only | N/A | REPLACEMENT_MARKDOWN_FENCE | False |
| sympy__sympy-13852 | local_only | N/A | REPLACEMENT_MARKDOWN_FENCE | False |
| concurrency_bug_02 | local_only | N/A | REPLACEMENT_MARKDOWN_FENCE | False |
| toy-math-solve | localheal_pipeline | EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE | none | False |
| task-a-real | local_committee_only | N/A | REPLACEMENT_MARKDOWN_FENCE | False |
| task-b-real | local_committee_only | N/A | REPLACEMENT_MARKDOWN_FENCE | False |

## Key Finding

**NO_REPRO_SCRIPT is GONE.** Pipeline now passes reproduction and reaches planning/patch synthesis.

`toy-math-solve` new failure: `EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE` — model returns empty response during patch synthesis.

## Pipeline Phase Progression (toy-math-solve)

```
Reproduction ✅ (skip_reproduction=True)
Planning ✅ (reached)
Localization ✅ (reached)
PatchSynthesis → model returns EMPTY_RESPONSE
Verification → not reached
```

## B8 Eligibility Assessment

Per B7.4 stop gate:
- `patch_synthesis_reached_count > 0` — YES (toy-math-solve reaches patch synthesis)
- Model output reaches parser — NO (empty response, not fence-wrapped)
- Failure is REPLACEMENT_MARKDOWN_FENCE — NO (failure is EMPTY_RESPONSE)

**B8 is NOT yet eligible.** The model returns empty response, not fence-wrapped output. B8 (prompt refinement for fence) would not help with empty responses.

## Explicit Statements

- No code changed in B7.4 (verification only).
- B8 not run.
- No public claim unless solved=true and verifier_result=pass.
- Pipeline reproduction contract is working — model response is the new blocker.

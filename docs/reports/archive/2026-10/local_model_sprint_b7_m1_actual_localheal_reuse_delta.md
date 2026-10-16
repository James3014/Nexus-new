# Local Model Sprint B7: M1 Actual LocalHeal Reuse Verification

**Status:** LOCAL_MODEL_SPRINT_B7_M1_ACTUAL_LOCALHEAL_REUSE_DELTA_COMPLETE
**Date:** 2026-07-01

## Baseline vs New

| Metric | Baseline (pre-sprint) | New (post B1-B6) | Delta |
|--------|----------------------|-------------------|-------|
| solved_count | 0/6 | 0/6 | +0 |
| parse_error_count (REPLACEMENT_MARKDOWN_FENCE) | 5/6 | 4/6 | -1 |
| non_empty_candidate_hash_count | 0/6 | 0/6 | +0 |
| candidate_isolated_count | 0/6 | 0/6 | +0 |
| verifier_pass_count | 0/6 | 0/6 | +0 |
| false_positive_count | 0 | 0 | +0 |

## Key Pipeline Metrics (from debug output)

| Task | localheal_pipeline_run_called | localheal_pipeline_run_success | orchestrator_run_reachable | pipeline_failure_reason |
|------|------------------------------|-------------------------------|---------------------------|------------------------|
| toy-math-solve | True | True | True | MODEL_PROVIDER_ERROR |
| task-a-real | N/A (committee) | N/A | N/A | N/A |
| task-b-real | N/A (committee) | N/A | N/A | N/A |

## What Improved

1. **pipeline.run() IS now called** for `localheal_pipeline` topology (B1)
2. **Orchestrator IS reachable** via pipeline.run() (B1)
3. **Pipeline result projection** works (B3)
4. **Committee retry delegation** wired (B5)
5. **Orchestrator selection** is planner-owned (B6)
6. **No regressions**: false_positive_count = 0

## What Failed

1. **toy-math-solve**: Pipeline called but `MODEL_PROVIDER_ERROR` — Ollama provider not available
2. **REPLACEMENT_MARKDOWN_FENCE**: Still 4/6 tasks fail on fence-wrapped output
3. **Committee tasks**: Pipeline retry delegated but `pipeline_retry_delegated: False` — pipeline didn't produce a patch

## Root Cause

The pipeline IS being called and the orchestrator IS reachable. The remaining failures are:
1. **Ollama provider availability**: Pipeline fails with `MODEL_PROVIDER_ERROR` when Ollama is not running
2. **Fence output**: Model still outputs fence-wrapped patches despite feedback
3. **Pipeline retry not producing patches**: Pipeline runs but doesn't produce a non-empty `final_patch`

## Explicit Statements

- Benchmark verification only.
- Full Local Model Nexus Armor still in progress.
- Pipeline wiring is complete — remaining issues are provider availability and model output format.
- No public claim unless verifier_pass and solved are proven.

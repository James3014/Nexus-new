# Local Model Sprint A6: M1 Verification Delta

**Status:** LOCAL_MODEL_SPRINT_A6_M1_VERIFICATION_DELTA_COMPLETE
**Date:** 2026-07-01

## Baseline vs New

| Metric | Baseline (pre-sprint) | New (post A1-A5) | Delta |
|--------|----------------------|-------------------|-------|
| solved_count | 0/6 | 0/6 | +0 |
| parse_error_count (REPLACEMENT_MARKDOWN_FENCE) | 5/6 | 5/6 | +0 |
| non_empty_candidate_hash_count | 0/6 | 0/6 | +0 |
| candidate_isolated_count | 0/6 | 0/6 | +0 |
| verifier_pass_count | 0/6 | 0/6 | +0 |
| false_positive_count | 0 | 0 | +0 |

## New Telemetry (post A1-A5)

| Field | Baseline | New | Notes |
|-------|----------|-----|-------|
| protocol_parse_error_kind | N/A | Present in 5/6 tasks | Now tracked |
| retry_available | N/A | True for committee tasks | Observational only |
| retry_not_invoked_reason | N/A | Empty (feedback builder available) | Observational only |
| localheal_pipeline_actual_execution | N/A | True for toy-math-solve | A3 bridge wired |
| localheal_pipeline_instantiated | N/A | True for toy-math-solve | A3 bridge wired |
| local_assist_telemetry | N/A | Present in all 6 tasks | A2 receipt wiring |
| route_truth_source | CapabilityPlanner | CapabilityPlanner | Unchanged |
| adapter_output_is_route_truth | False | False | Unchanged |

## Key Observations

1. **Solved rate unchanged (0/6)**: Expected — A1-A5 are wiring/seam stages, not solve-rate improvement stages.
2. **REPLACEMENT_MARKDOWN_FENCE remains dominant failure**: 5/6 tasks fail on fence-wrapped output.
3. **localheal_pipeline topology now has actual execution**: A3 bridge wires real provider through HealPipeline.
4. **Retry metadata now observable**: A5 adds retry_available/retry_not_invoked_reason to committee path.
5. **Receipt telemetry now present**: A2 wires local_assist_telemetry into all executor paths.
6. **No regressions**: No false positives, no new failure modes.

## Stop Gate Assessment

- false_positive_count = 0: No regression.
- solved_count unchanged: No regression.
- All new telemetry is observational only.
- Ready for next phase (actual retry integration or prompt improvement).

## Explicit Statements

- Benchmark verification only.
- Full Local Model Nexus Armor still in progress.
- 0/6 solved is expected at this stage — wiring is complete, retry integration is next.

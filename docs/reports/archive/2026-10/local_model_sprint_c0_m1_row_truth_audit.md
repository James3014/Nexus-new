# Local Model Sprint C0: M1 Row Truth Audit

**Status:** LOCAL_MODEL_SPRINT_C0_M1_ROW_TRUTH_AUDIT_COMPLETE
**Date:** 2026-07-01

## M1 Row Keys (all 6 tasks now identical)

All 6 tasks have 44 keys including B7.7 projected fields:
- `phase_reached`, `patch_synthesis_reached`, `patch_synthesis_provider_error`
- `patch_synthesis_model_called`, `patch_synthesis_output_len`, `patch_synthesis_prompt_len`
- `patch_synthesis_model_name`, `pipeline_failure_reason`, `pipeline_final_patch_len`
- `pipeline_run_called`, `pipeline_run_success`, `orchestrator_run_reachable`
- `provider_error`, `provider_invoked`, `model_name_used`, `output_len`, `prompt_len`, `timed_out`

## Task-Level Evidence

| Task | phase_reached | patch_synthesis_reached | provider_invoked | model_called | prompt_len | output_len | pipeline_failure_reason |
|------|--------------|------------------------|-----------------|-------------|-----------|-----------|------------------------|
| astropy | "" | False | False | False | 0 | 0 | REFUSAL_DETECTED |
| sympy | "" | False | False | False | 0 | 0 | "" |
| concurrency | "" | False | False | False | 0 | 0 | "" |
| toy-math-solve | "" | False | False | False | 0 | 0 | EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE |
| task-a-real | "" | False | False | False | 0 | 0 | REFUSAL_DETECTED |
| task-b-real | "" | False | False | False | 0 | 0 | REFUSAL_DETECTED |

## Key Findings

1. **All 6 rows have phase telemetry** — B7.7 projection works ✅
2. **`phase_reached` is empty for all 6** — phase telemetry not being set by pipeline ❌
3. **`patch_synthesis_reached: False` for all 6** — pipeline never reaches patch synthesis ❌
4. **`provider_invoked: False` for all 6** — provider never called through bridge ❌
5. **`prompt_len: 0` for all 6** — no prompt sent to model ❌
6. **`output_len: 0` for all 6** — no output from model ❌
7. **`pipeline_run_called: True` for toy-math-solve** — pipeline.run() was called ✅
8. **`pipeline_run_success: True` for toy-math-solve** — pipeline returned without exception ✅
9. **`orchestrator_run_reachable: True` for toy-math-solve** — orchestrator was reachable ✅

## Contradictions Resolved

| Previous Report | C0 Finding | Resolution |
|----------------|------------|------------|
| B7.4: patch_synthesis reached | C0: patch_synthesis_reached=False | B7.4 was wrong — pipeline did NOT reach patch synthesis |
| B7.5: raw_model_metadata has telemetry | C0: rows now have telemetry | B7.7 fixed this — rows now carry telemetry |
| B7.6: EMPTY_RESPONSE is model empty | C0: provider_invoked=False, prompt_len=0 | EMPTY_RESPONSE is pipeline-internal, not model output |
| B7.8: provider NOT called | C0: confirmed provider_invoked=False | B7.8 was correct |

## No Code Changed

This stage is audit only.

# Local Model Sprint B3: Project HealPipeline Result into Executor Response

**Status:** LOCAL_MODEL_SPRINT_B3_PIPELINE_RESULT_PROJECTION_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Pipeline result projected into executor response |
| `tests/unit/local_heal/test_localheal_pipeline_seam_truth.py` | Added 4 B3 projection tests |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_localheal_pipeline_seam_truth.py -q
# 27 passed
```

## What Changed

| Before B3 | After B3 |
|-----------|----------|
| Pipeline result ignored, executor generates own patch | Pipeline `final_patch` used if non-empty |
| `pipeline_final_patch` only in bridge telemetry | `pipeline_final_patch` projected into `raw_meta` |
| `pipeline_solve_eligible` only in bridge telemetry | `pipeline_solve_eligible` projected into `raw_meta` |
| `pipeline_failure_reason` only in bridge telemetry | `pipeline_failure_reason` projected into `raw_meta` |
| `reasoning_summary` always "selected_by_..." | `reasoning_summary` = "pipeline_result" or "provider_generated" |

## Projection Rules

1. If `pipeline_final_patch` is non-empty → use as `candidate_patch`, compute `candidate_hash`
2. If `pipeline_final_patch` is empty → fall back to provider-generated patch
3. `pipeline_solve_eligible` projected but NOT used to set `solved` (requires verifier)
4. `pipeline_failure_reason` projected for observability
5. Exception remains fail-closed

## Explicit Statements

- No new route/topology/parser/sanitizer.
- solved rate not claimed.
- Pipeline result projected, not forced.

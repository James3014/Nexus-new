# Local Model Sprint A3: localheal_pipeline Bridge to Existing HealPipeline.run

**Status:** LOCAL_MODEL_SPRINT_A3_LOCALHEAL_PIPELINE_PROJECTION_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_capability_context.py` | Added `provider` field to context |
| `nexus/services/local_heal/local_model_capability_executors.py` | Bridge now uses real provider instead of `_noop_generate` |
| `nexus/services/local_heal/local_model_executor.py` | Passes provider to capability context |
| `tests/unit/local_heal/test_localheal_pipeline_seam_truth.py` | Added 7 A3 bridge tests |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_localheal_pipeline_seam_truth.py tests/unit/local_heal/test_local_model_executor.py tests/unit/local_heal/test_downstream_enforcement_gates.py -q
# 47 passed
```

## Test Counts

- `test_localheal_pipeline_seam_truth.py`: 14 passed (7 existing + 7 new)
- `test_local_model_executor.py`: 25 passed
- `test_downstream_enforcement_gates.py`: 8 passed

## Bridge Behavior

| Condition | Before A3 | After A3 |
|-----------|-----------|----------|
| Provider available | `_noop_generate` | Real `provider.generate()` wrapper |
| Provider unavailable | `_noop_generate` | `_noop_generate` (unchanged) |
| HealPipeline instantiation | Creates pipeline with noop | Creates pipeline with real provider fn |
| Non-pipeline topology | Returns availability-only | Returns availability-only (unchanged) |

## Explicit Statements

- Existing HealPipeline reused. No new pipeline created.
- No new route/topology/parser/retry loop added.
- localheal_pipeline is still planner-owned downstream projection.
- route_truth_source remains CapabilityPlanner.
- adapter_output_is_route_truth remains False.
- Fail-closed on pipeline instantiation error.

# Local Model Sprint B2: Pipeline Telemetry Semantics

**Status:** LOCAL_MODEL_SPRINT_B2_PIPELINE_TELEMETRY_SEMANTICS_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_capability_executors.py` | `actual_execution` now requires `pipeline_run_success` |
| `tests/unit/local_heal/test_localheal_pipeline_seam_truth.py` | Added 4 B2 telemetry semantics tests |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_localheal_pipeline_seam_truth.py -q
# 23 passed
```

## Telemetry Semantics (after B2)

| Field | Meaning |
|-------|---------|
| `localheal_pipeline_instantiated` | Pipeline object was created |
| `localheal_pipeline_run_called` | `pipeline.run()` was called |
| `localheal_pipeline_run_success` | `pipeline.run()` returned without exception |
| `localheal_pipeline_actual_execution` | Requires `run_success=True` AND `len(invoked_modules) >= 2` |
| `orchestrator_run_reachable` | Pipeline entered orchestrator path |
| `semantic_retry_invoked` | False by default — only from orchestrator telemetry |

## Key Change

Before B2: `actual_execution = path_a_actual_execution and len(invoked_modules) >= 2`
After B2: `actual_execution = pipeline_run_success and len(invoked_modules) >= 2`

This means:
- Instantiation alone does NOT set `actual_execution=True`
- `run_called=True` does NOT imply `run_success=True`
- `actual_execution=True` ONLY when `run_success=True`

## Explicit Statements

- No execution behavior changed.
- No retry implemented.
- Telemetry is now truthful.

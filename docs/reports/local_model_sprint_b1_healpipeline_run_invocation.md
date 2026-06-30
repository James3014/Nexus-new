# Local Model Sprint B1: Planner-owned HealPipeline.run Invocation

**Status:** LOCAL_MODEL_SPRINT_B1_HEALPIPELINE_RUN_INVOCATION_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_capability_executors.py` | Bridge now calls `pipeline.run(heal_ctx)` with valid HealContext |
| `tests/unit/local_heal/test_localheal_pipeline_seam_truth.py` | Updated tests for B1 behavior |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_localheal_pipeline_seam_truth.py tests/unit/local_heal/test_local_model_executor.py tests/unit/local_heal/test_downstream_enforcement_gates.py -q
# 52 passed
```

## What Changed

| Before B1 | After B1 |
|-----------|----------|
| Bridge instantiates `HealPipeline(...)` | Bridge instantiates AND calls `pipeline.run(heal_ctx)` |
| `localheal_pipeline_run_called` not tracked | `localheal_pipeline_run_called` tracked |
| `localheal_pipeline_run_success` not tracked | `localheal_pipeline_run_success` tracked |
| `orchestrator_run_reachable` not tracked | `orchestrator_run_reachable` tracked |
| `pipeline_final_patch` not tracked | `pipeline_final_patch` from result tracked |
| `pipeline_solve_eligible` not tracked | `pipeline_solve_eligible` from result tracked |
| `pipeline_failure_reason` not tracked | `pipeline_failure_reason` from result tracked |

## HealContext Construction

Bridge builds `LegacyHealContext` from `LocalModelCapabilityContext`:
- `instance_id` = `ctx.task_id`
- `repo_dir` = `Path(ctx.source_root)`
- `problem_statement` = `ctx.problem_statement`
- `route_context` = `ctx.route_context`
- `max_tries` = 3

## NEXUS_USE_COMMITTEE Risk

Line 201 of `pipeline.py`: `orchestrator_cls = CommitteeOrchestrator if os.getenv("NEXUS_USE_COMMITTEE", "0") == "1" else HealOrchestrator`

This is **NOT addressed in B1** — reported as residual risk for B6.

## Explicit Statements

- No new route/topology/parser/sanitizer.
- solved rate not claimed.
- HealPipeline.run() IS now called.
- Orchestrator.run() IS reachable via pipeline.run().
- NEXUS_USE_COMMITTEE remains a residual risk for B6.

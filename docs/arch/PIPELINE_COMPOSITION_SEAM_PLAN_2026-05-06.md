# Pipeline Composition Seam Plan - P19

Status: inventory complete, implementation deferred until after Flash A/B.

## Current Runtime Reality

- `NexusPipeline` still inherits `PipelineStagesMixin`, `PipelineRepairMixin`, `PipelineCrystalMixin`, and `PipelineResearchMixin`.
- `PhaseExecutor` and `HandlerPhaseExecutor` already provide the composition seam.
- P, X, D, R, and A have composition-backed execution paths.
- C still runs through `_stage_crystallize` after the R/A loop and is not yet a first-class executor.
- S exists as runtime metadata (`stage_flow`, `stage_descriptions`, `stage_status`, `decision_journal`) rather than a separate executor.

## Phase Coupling Map

| Phase | Current owner | Primary inputs | Primary outputs | Composition status |
| --- | --- | --- | --- | --- |
| S | `pipeline.py` metadata bootstrap | `NexusState`, task metadata | stage flow/status, journal | Metadata seam only |
| P | `PlannerPhaseHandler` / `_stage_plan` | task, kwargs, policy | `ctx.prediction`, research route | Executor seam active |
| X | `ResearchPhaseHandler` / `_stage_research` | research route, benchmark force | `ctx.research_pack` | Executor seam active |
| D | `DiagnosticPhaseHandler` / `_stage_diagnose` | prediction, research pack | `ctx.pack` diagnosis | Executor seam active |
| R | `RepairPhaseHandler` / `PipelineRepairMixin` | diagnosis, retry state | patch result, decision ids | Executor seam active inside R/A loop |
| A | `AuditPhaseHandler` / `PipelineRepairMixin` | R result, evidence bundle | approval/rejection | Executor seam active inside R/A loop |
| C | `PipelineCrystalMixin` | final success, tracer | learning crystallization | Legacy mixin only |

## Safe Refactor Order

1. C executor: lowest behavioral risk because it runs after terminal success/failure is already known.
2. S executor: convert metadata bootstrap into an explicit seed executor after C is stable.
3. P executor hardening: make planner executor the default and keep legacy `_stage_plan` as fallback for one release.
4. X executor hardening: preserve existing research-route gating and benchmark-force semantics.
5. D executor hardening: keep binder ownership of `ctx.pack` explicit.
6. R executor extraction: split only one repair-loop branch at a time.
7. A executor extraction: keep fail-closed behavior before deleting legacy audit paths.
8. Remove mixin inheritance only after all phases have executor coverage and equivalence tests.

## Gates For Each Slice

- `uv run pytest -q tests/engine/test_phase_plugin.py tests/engine/test_phase_executors.py tests/engine/test_pipeline_composition.py tests/engine/test_pipeline_stage_flow.py`
- `uv run python scripts/ops/nexus_pre_flash_gate.py --quick`
- No new Mixin class or direct phase method call may be introduced.
- Each phase migration must include an equivalence test proving legacy behavior is preserved for the changed phase.

## Deferred Until After Flash

- Deleting mixin inheritance.
- Moving the entire R/A loop at once.
- Rewriting CLI orchestration around phase executors.
- Treating this document as proof of implementation; implementation proof must come from runtime tests and receipts.

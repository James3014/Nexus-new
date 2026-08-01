# Task Card: runtime-phase-transition-integration

artifact_authority: draft-successor
owner: James Chen
status: DRAFT_PENDING_OWNER_ACTIVATION
task_id: runtime-phase-transition-integration
commit_required: true
AUTO_CHAIN: false

## Objective

Make the existing Pipeline consult the frozen contract for phase start/end,
research continuation, audit rejection and hard/recoverable block behavior
without creating a second executor or changing route authority.

## Allowed files

- `nexus/engine/pipeline.py`
- `nexus/engine/pipeline_repair.py`
- `nexus/engine/runtime_phase_contract.py`
- `tests/engine/test_pipeline_phase_contract.py`
- `tests/engine/test_pipeline_stage_flow.py`

## Verification

```bash
uv run pytest -q tests/engine/test_pipeline_phase_contract.py tests/engine/test_pipeline_stage_flow.py
git diff --check
```

## Exit criteria

No illegal transition reaches an executor; `A → R`, `A → D`, `D → X → D`,
`RECOVERABLE_BLOCK` and `HARD_BLOCK` are covered by deterministic tests, and
existing successful pipeline behavior remains equivalent.

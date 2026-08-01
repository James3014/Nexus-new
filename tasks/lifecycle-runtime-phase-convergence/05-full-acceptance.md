# Task Card: runtime-full-acceptance

artifact_authority: draft-successor
owner: James Chen
status: DRAFT_PENDING_OWNER_ACTIVATION
task_id: runtime-full-acceptance
commit_required: true
AUTO_CHAIN: false

## Objective

Run the complete runtime/development/memory acceptance matrix after Cards 0–4
and current P7 disposition are independently verified.

## Allowed files

- `scripts/ops/nexus_runtime_lifecycle_acceptance.py`
- `tests/engine/test_runtime_phase_contract.py`
- `tests/engine/test_pipeline_phase_contract.py`
- `tests/engine/test_pipeline_phase_hooks.py`
- `tests/engine/test_runtime_learning_closure.py`
- `docs/arch/LIFECYCLE_RUNTIME_PHASE_CONTRACT.md`

## Verification

```bash
uv run pytest -q tests/engine/test_runtime_phase_contract.py tests/engine/test_pipeline_phase_contract.py tests/engine/test_pipeline_phase_hooks.py tests/engine/test_runtime_learning_closure.py
uv run python scripts/ops/nexus_runtime_lifecycle_acceptance.py
git diff --check
```

## Exit criteria

Read-only, Direct, Assisted, Isolated Candidate, reconnect, timeout,
definition drift, approval rejection, Candidate disposition, `A → R`,
`A → D`, `D → X → D`, `HARD_BLOCK`, `RECOVERABLE_BLOCK` and terminal C side
effects all pass with receipt-bound evidence. No public or production claim is
made by the worker.

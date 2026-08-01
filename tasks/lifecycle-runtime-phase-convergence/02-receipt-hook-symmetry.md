# Task Card: runtime-phase-receipt-hook-symmetry

artifact_authority: draft-successor
owner: James Chen
status: DRAFT_PENDING_OWNER_ACTIVATION
task_id: runtime-phase-receipt-hook-symmetry
commit_required: true
AUTO_CHAIN: false

## Objective

Emit phase-bound receipts and symmetric observer hooks while keeping
enforcement synchronous and fail-closed on the action/state path.

## Allowed files

- `nexus/events/contracts.py`
- `nexus/engine/pipeline.py`
- `nexus/engine/phase_handshake.py`
- `nexus/engine/execution/receipt_augmenter.py`
- `tests/events/test_lifecycle_phase_receipts.py`
- `tests/engine/test_pipeline_phase_hooks.py`

## Verification

```bash
uv run pytest -q tests/events/test_lifecycle_phase_receipts.py tests/engine/test_pipeline_phase_hooks.py
git diff --check
```

## Exit criteria

Every phase has start/end/fail/retry/block/cancel/timeout/reconcile evidence
where applicable; observer failure cannot mutate authority; incomplete receipt
or drift fails closed.

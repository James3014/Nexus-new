# Task Card: runtime-phase-receipt-hook-symmetry

artifact_authority: current
owner: James Chen
status: VERIFIED_CANDIDATE
task_id: runtime-phase-receipt-hook-symmetry
commit_required: true
AUTO_CHAIN: false
candidate_commit: dd420b3dd9fe898dac450dfbe73d6bfade7e7c3d
claim_ceiling: IMPLEMENTER_VERIFIED_RUNTIME_PHASE_RECEIPT_HOOK_CANDIDATE

verification_receipt:
  base_head: a35c3c82a12e59abd9e3cacc0f99d2804cbab612
  card_hash_at_execution: f4796774a54c3ac613c9c3bdf77cc4e82d4699d67d9ee7020dfa74d8728f23e7
  focused_tests: 6 passed
  affected_regression: 33 passed
  diff_check: PASS
  evidence_scope: phase_receipts_observer_symmetry_receipt_completeness_and_c_terminal_hooks
  external_acceptance: DEFERRED_EXTERNAL_ACCEPTANCE

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

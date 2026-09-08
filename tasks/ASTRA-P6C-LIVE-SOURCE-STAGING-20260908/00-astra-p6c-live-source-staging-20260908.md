# Task Card: astra-p6c-live-source-staging-20260908

artifact_authority: current
task_id: `astra-p6c-live-source-staging-20260908`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Phase2 of Owner-approved P5/P6 isolated source staging. Port exactly accepted P6-C delta 6724256fd3380c615c217f5de257493963211e54..1b055a4d6e129a00c0637785609b233b55f2a3c5 onto independently accepted P6AB source60e6e722baad97f7b078cf261860b3a985f1898c derived from deployedbea9ae7a6742929785d40840da79cff4faefa485. Preserve newer live-base/P6AB changes via semantic three-way deltas, no whole existing donor-file replacement or history merge. Bind opt-in explicit root/owner context for task state, event log and Runtime receipts; monotonic writer generation, fixed lock order, append-only preservation, no unresolved-effect rollback, crash/reconcile and original readonly behavior must remain. Do not change Planner/gateway/policy/route/executor/lifecycle authority. P5 extraction separate. No provider/native/API-key/SDK/Agy/network/live state/deployment/config/main/push/merge/approval/integration. Worker may commit scoped source only, never self-accept. Source staging is not live writer transition. Out-of-scope semantic dependencies must be reported, not overwritten. Reuse all accepted P6C failure/process/rollback tests and run compatibility suite on exact current base.

## Allowed files

- `nexus/events/log_store.py`
- `nexus/events/state_owner_manifest.py`
- `nexus/events/writer_generation.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/services/unified_runtime.py`
- `tests/events/test_log_store_generation.py`
- `tests/events/test_state_owner_manifest.py`
- `tests/integration/test_p6c_state_consistency.py`
- `tests/nexus/orchestrator/test_self_hosted_state_owner.py`

## Verification commands

```bash
python3 -m pytest -q tests/events/test_state_owner_manifest.py tests/events/test_log_store_generation.py tests/integration/test_p6c_state_consistency.py tests/nexus/orchestrator/test_self_hosted_state_owner.py
python3 -m pytest -q tests/core/test_event_bus.py tests/events/test_effect_journal.py tests/events/test_event_writer_generation.py tests/integration/test_event_fence_runtime.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/services/test_unified_runtime_effect_fence.py tests/services/test_unified_runtime.py tests/services/test_mainchain_entry.py
python3 -m compileall -q nexus/events nexus/services/unified_runtime.py nexus/orchestrator/self_hosted_task_service.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

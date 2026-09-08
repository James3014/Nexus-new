# Task Card: astra-p6ab-live-source-staging-r2-20260908

artifact_authority: current
task_id: `astra-p6ab-live-source-staging-r2-20260908`
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

Phase 1 of approved P5/P6 staging: port only accepted P6-A writer-generation and P6-B effect-journal deltas from frozen qualified source1b055a4d6e129a00c0637785609b233b55f2a3c5 and their original scoped commits94aaced105ac33a475eb61323b816379633f708d/a3d045674b6a29edb3aa784c60d740b3951ae920 into isolated detached source based on deployedbea9ae7a6742929785d40840da79cff4faefa485. Preserve newer live-base changes, no wholesale donor-file replacement or history merge. Keep monotonic generation/CAS, stale-writer rejection, fixed lock order, effect PREPARED/COMMITTED/UNKNOWN/lost-ACK reconcile and no duplicate irreversible effects. Preserve original opt-in and unsupported behavior. No P6-C state-owner or P5 payload rewrites in this phase. No Planner/gateway/policy/route/executor authority changes; no provider/API-key/SDK/Agy/network/live-state/deployment/config/main/push/merge/approval/integration operations. Worker may scoped source commit only. Full tests plus actual child-process and fault/replay coverage on this exact base required. Later P6-C and P5 need separate scoped cards under the same overall goal, not inferred completion. Return out-of-scope dependency precisely without overriding existing live code. Correction of first staging scope: include log_store.py writer_generation/enforce_generation API required by original accepted P6-A. Use the P6-A delta, not final P6-C owner_context code. The earlier nine-file card cannot complete this dependency; this ten-file successor governs the implementation. Preserve no-live-effects and no wider authority changes.

## Allowed files

- `nexus/events/effect_journal.py`
- `nexus/events/writer_generation.py`
- `nexus/events/transport.py`
- `nexus/events/log_store.py`
- `nexus/services/unified_runtime.py`
- `tests/core/test_event_bus.py`
- `tests/events/test_effect_journal.py`
- `tests/events/test_event_writer_generation.py`
- `tests/integration/test_event_fence_runtime.py`
- `tests/services/test_unified_runtime_effect_fence.py`

## Verification commands

```bash
python3 -m pytest -q tests/core/test_event_bus.py tests/events/test_effect_journal.py tests/events/test_event_writer_generation.py tests/integration/test_event_fence_runtime.py tests/services/test_unified_runtime_effect_fence.py tests/services/test_unified_runtime.py
python3 -m compileall -q nexus/events nexus/services/unified_runtime.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

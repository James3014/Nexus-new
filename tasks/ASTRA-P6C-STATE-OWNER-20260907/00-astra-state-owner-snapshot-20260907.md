# Task Card: astra-state-owner-snapshot-20260907

artifact_authority: current
task_id: `astra-state-owner-snapshot-20260907`
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

Implement source-owned opt-in state-owner manifest/snapshot/reconcile/restore for explicit selected task-state, EventStore and Runtime receipt roots; no fixture backup substitution. Base qualified4887 plus accepted P6-A94aaced105ac33a475eb61323b816379633f708d. Coordinator may transport exact card/INDEX. Phase1 only new state_owner_manifest.py and its test, no common-file edits. Phase2 common-file wiring waits for coordinator exact accepted P4/P6-B dependency binding; no final acceptance until actual owner paths/crash matrix proven. Luna source implementation only, scoped commits; no model/API-key/SDK/Agy/network/live state/production restore/deployment/main/push/merge/approval. Explicit StateOwnerBinding(owner_id,root,generation,transaction_id); no cwd/defaultroot fallback. Source-owned closed store roles/allowlist, immutable versioned manifest with previous committed digest, per-file path,size,SHA,owner/generation/transaction. No caller flag can relabel event/effect history rollbackable. Persist PREPARED/fsync before selected store writes; COMMITTED only after all selected files fsync and exact digest readback; atomic replace/directory fsync. Shared fixed lock order integrates existing claim/event locks without deadlock; bounded acquisition, stalegeneration denial before any store bytes change, strict owner/path/symlink/nonregular denial. Generation token shared with P6-A; do not reset generation backwards or silently fallback when opted-in binding missing. Normal legacy mode unchanged. Existing task _write_state_locked and Runtime receipt writes use the actual port; read/replan binds receipt lineage and generation. Recovery only classifies ABSENT/PREPARED_UNKNOWN/COMMITTED using source-owned manifest and physical hashes, no effects or success inference on partial stores. Preserve committed append-only event/effect records on incremental rollback; restore only source-designated mutable state from known committed snapshot using new monotonic generation/transaction and recovery-only quarantine that cannot trigger automatic task execution/approval/provider calls. Any post-snapshot irreversible progress or unresolved effect denies destructive rollback and requires reconcile-only. Restore is explicit bounded API, never automatic on startup. Crash tests actual child os._exit at prepare,task state,event fsync,receipt,commit boundaries through actual task/runtime owner paths in temp roots; verify restart status, hashes, retained append-only history, no-new-effect, oldwriter zero-byte denial, no lock leaks. Missing/tampered/cross-owner/cross-root manifest fails closed. Full verifier and root independent behavioral/diff acceptance required; Phase1 module tests alone do not close P6-C or imply live cutover.

## Allowed files

- `nexus/events/state_owner_manifest.py`
- `nexus/events/writer_generation.py`
- `nexus/events/log_store.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/services/unified_runtime.py`
- `tests/events/test_state_owner_manifest.py`
- `tests/events/test_log_store_generation.py`
- `tests/nexus/orchestrator/test_self_hosted_state_owner.py`
- `tests/integration/test_p6c_state_consistency.py`

## Verification commands

```bash
python3 -m pytest -q tests/events/test_state_owner_manifest.py tests/events/test_log_store_generation.py tests/nexus/orchestrator/test_self_hosted_state_owner.py tests/integration/test_p6c_state_consistency.py
python3 -m pytest -q tests/events/test_event_writer_generation.py tests/core/test_event_bus.py tests/services/test_unified_runtime.py tests/nexus/orchestrator/test_self_hosted_task_service.py
python3 -m compileall -q nexus/events nexus/services/unified_runtime.py nexus/orchestrator/self_hosted_task_service.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

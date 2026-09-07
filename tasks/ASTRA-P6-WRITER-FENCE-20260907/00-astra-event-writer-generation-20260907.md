# Task Card: astra-event-writer-generation-20260907

artifact_authority: current
task_id: `astra-event-writer-generation-20260907`
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

Implement opt-in source-owned EventStore writer-generation fencing for Astra P6-A. Source subject 4887d8f6a3faf50d6b600f2c170526e08d4bf408 plus these exact coordinator-created card/index bytes in an isolated Luna worktree; coordinator may transport this card-only commit. NexusEventBus._log_store is owner; persisted generation manifest is <project_root>/.nexus/events/event_log.generation.v1.json under existing EventStore lock. Explicit configure(writer_generation=...,enforce_generation=True), validated generation install/advance CAS API, no automatic reset or runtime-live activation. Persist complete versioned manifest binding; stale/missing/malformed/symlink generation must deny before append bytes/tail change. Generation check and append must share lock to avoid race. Preserve existing unfenced callers when no manifest exists; once a manifest is installed, legacy writers must not bypass its fence. Bind append record generation without silently rewriting historical log rows. Existing EventStore digest/restart contracts stay valid. Test independent competing writers, epoch advance rejecting stale existing writer, unfenced writer denial after opt-in, fresh re-open, missing/invalid manifest, CAS conflict, and unchanged bytes on denial. Tests use temporary project roots, no live state/production migration. This card grants bounded source implementation and scoped commit only, not local lifecycle Candidate/admission/approval/integration/merge/deploy. No API-key model calls or provider SDK calls. Independent coordinator verification and exact diff review required. P6-B effects/restore remain downstream.

## Allowed files

- `nexus/events/log_store.py`
- `nexus/events/writer_generation.py`
- `nexus/events/transport.py`
- `tests/events/test_event_writer_generation.py`
- `tests/core/test_event_bus.py`

## Verification commands

```bash
python3 -m pytest tests/events/test_event_writer_generation.py tests/core/test_event_bus.py -q
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

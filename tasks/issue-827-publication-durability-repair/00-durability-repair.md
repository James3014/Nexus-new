# Task Card: durability-repair

artifact_authority: current
task_id: `durability-repair`
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

Owner explicitly reaffirmed all operations necessary to complete Issue 827 in this thread after the earlier scope rejection. Repair supported publication durability and exact prepared-operation binding defects on b1136391823b7437680aa02b8b5c5d2ca349df54. Luna implements; controller independently verifies. Fsync containing directory after atomic replace using existing donor pattern; fail closed on durable write errors before dispatch; reject prepared operation/proposal/store identity mismatch and unknown remote outcome states without blind redispatch. Preserve exact Owner signature, one-shot/replay, readback-only lost ACK, internal collaboration and DevSpace UNKNOWN_BLOCKED. No new protocol, no live third-party publication, no merge or release through this card. Require regression RED/GREEN and scoped immutable commit.

## Allowed files

- `nexus/orchestrator/owner_representation.py`
- `tests/nexus/orchestrator/test_owner_representation.py`
- `docs/governance/OWNER_REPRESENTATION.md`

## Verification commands

```bash
python -m pytest -q tests/nexus/orchestrator/test_owner_representation.py tests/nexus/executors/test_cli_worker.py
python -m ruff check nexus/orchestrator/owner_representation.py tests/nexus/orchestrator/test_owner_representation.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

# Task Card: owner-oracle-repair

artifact_authority: current
task_id: `owner-oracle-repair`
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

Owner authorized repair in this task: repair PR 829 Candidate 2a49606cd503844643ddca5e8974f12d6cbbe0e3 for Issue 827. Luna implements; primary coordinator independently verifies. Require independently rooted exact Owner authorization, reject self-issued and in-memory-only authorization, preserve one-shot replay and readback-only lost ACK, internal collaboration and DevSpace UNKNOWN_BLOCKED. Reuse existing signing/trust primitives where applicable; no live third-party publication. Produce regression RED then GREEN, scoped immutable commit and independent acceptance; no merge authority is granted by this card.

## Allowed files

- `nexus/contracts/owner_representation.py`
- `nexus/orchestrator/owner_representation_store.py`
- `tests/nexus/orchestrator/test_owner_representation.py`
- `docs/governance/OWNER_REPRESENTATION.md`

## Verification commands

```bash
python -m pytest -q tests/nexus/orchestrator/test_owner_representation.py tests/nexus/executors/test_cli_worker.py
python -m ruff check nexus/contracts/owner_representation.py nexus/orchestrator/owner_representation_store.py tests/nexus/orchestrator/test_owner_representation.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

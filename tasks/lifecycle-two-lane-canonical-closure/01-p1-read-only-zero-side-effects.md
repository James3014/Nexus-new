# Task Card 01: P1 Read-only Zero Side-effects

## Identity

- task_id: `lifecycle-two-lane-p1-read-only-zero-side-effects`
- campaign_id: `lifecycle-two-lane-canonical-closure`
- artifact_authority: current
- status: COMPLETED
- owner: James Chen
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Make lifecycle inventory, convergence-plan, slot-status, and state-root reads physically side-effect free. Read-only calls must not create Target roots, acquire lifecycle locks, reconcile tasks, or classify preserved nested evidence as a current authority conflict.

## Allowed files

- `tasks/lifecycle-two-lane-canonical-closure/01-p1-read-only-zero-side-effects.md`
- `nexus/orchestrator/worktree_manager.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`

## Verification

```bash
git diff --check
pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'workspace_inventory or state_root_inventory'
pytest -q tests/nexus/orchestrator/test_worktree_manager.py -k 'workspace_inventory or reusable_slot_status'
```

## Exit criteria

Missing Target roots remain absent after all three read-only workspace calls; state-root authority conflicts are reported only for multiple canonical authority entries; preserved rehearsal/archive duplicates are evidence-only; focused tests pass; and a scoped commit exists.

## Block classification

Any read-only API that still creates a directory, lock, reconciliation event, or false authority conflict is a `HARD_BLOCK`; preserve the failing evidence and do not broaden the allowed scope.

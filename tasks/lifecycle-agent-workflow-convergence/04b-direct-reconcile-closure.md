# Task Card: lifecycle-workflow-p4b-direct-reconcile-closure

artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: lifecycle-workflow-p4b-direct-reconcile-closure
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Make `DIRECT_RECONCILE_REQUIRED` a resolvable recovery state. A formal
`nexus_task_reconcile` call must inspect canonical evidence without replaying a
mutation, close a no-mutation provider/transport failure into an existing
terminal `FINAL_BLOCK` disposition that can be retried with the same task id,
and retain unsafe or ambiguous evidence for review.

## Authority and boundaries

- `SelfHostedTaskService` remains the only lifecycle state authority.
- No direct JSON edits, automatic retry, Target creation, approval,
  integration, push, or cleanup of unrelated work.
- No-mutation closure requires the expected base to be an ancestor and the
  task's allowed paths to be absent from commits since base and all staged or
  working-tree changes.
- Ambiguous or touched evidence stays fail-closed and does not become retryable.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tasks/lifecycle-agent-workflow-convergence/INDEX.md`
- `tasks/lifecycle-agent-workflow-convergence/04b-direct-reconcile-closure.md`

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p4b-pycache uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
```

## Exit criteria

- Reconcile is idempotent and never invokes the provider or replays a commit.
- Safe provider failure becomes `FINAL_BLOCK` with
  `reconciliation_status=RECONCILED`, `reconciliation_required=false`,
  `cleanup_decision=ALREADY_REMOVED`, and `next_action=retry_same_task`.
- Unsafe/ambiguous evidence remains `DIRECT_RECONCILE_REQUIRED` with a review
  action and no mutation.
- Same `task_id` retry creates a new attempt rather than a duplicate task.

## Block classification

- `RECOVERABLE_BLOCK`: focused service/test failure.
- `HARD_BLOCK`: evidence cannot distinguish the task mutation from unrelated
  canonical changes, or any proposal would replay without reconciliation.

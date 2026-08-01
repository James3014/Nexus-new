# Task Card: lifecycle-workflow-p2-durable-canonical-actions

artifact_authority: current
owner: James Chen
status: PENDING
task_id: lifecycle-workflow-p2-durable-canonical-actions
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Make Direct and Assisted canonical mutations restartable and idempotent without
creating a Target. Record intent, application, verification, commit, and
reconciliation in the existing lifecycle state service.

## Dependencies

- `lifecycle-workflow-p1-action-envelope` integrated.
- `tasks/bootstrap-authority-convergence/08-orphan-workspace-reconciliation.md`
  and its pre-P2 bootstrap/context optimization gate owner-reviewed.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_workflow_repair.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p2-pycache uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_workflow_repair.py tests/nexus/orchestrator/test_unified_mcp_gateway.py
git diff --check
```

## Exit criteria

Direct/Assisted state is Target-free, duplicate finish is idempotent, and
disconnect/unknown action requires reconcile before retry.

## Block classification

- `HARD_BLOCK`: existing state authority cannot represent the action safely.
- `RECOVERABLE_BLOCK`: provider/test failure with state preserved.

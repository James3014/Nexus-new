# Task Card: lifecycle-workflow-p2-durable-canonical-actions

artifact_authority: current
owner: James Chen
status: VERIFIED_PENDING_OWNER_REVIEW
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
- `tasks/bootstrap-authority-convergence/09-context-budget-and-overlay-gates.md`
  integrated and owner-reviewed after the orphan inventory gate.

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

## Verified evidence

- Verification HEAD `d596bb7f7948fa1cf1060a6fa04f637c1c74641b` was clean.
- Revision-bound manifest `/tmp/nexus-p2-gate-d596.json` reported
  `nexus.fresh_suite_manifest.v1`, `PASS`, 163 passed, 0 failed, 0 skipped.
- The exact verification command in this card was covered by the fresh-suite
  collection and execution; no Target was created by the Direct/Assisted tests.

Promotion remains owner-gated because the bootstrap overlay card and this card
still require explicit lifecycle acceptance.

## Block classification

- `HARD_BLOCK`: existing state authority cannot represent the action safely.
- `RECOVERABLE_BLOCK`: provider/test failure with state preserved.

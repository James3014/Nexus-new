# Task Card: lifecycle-concurrency-dispatch-corrective

artifact_authority: current
task_id: `lifecycle-concurrency-dispatch-corrective`
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

Fix three lifecycle regressions as one governed TDD packet: allow ISOLATED_TARGET creation from committed canonical HEAD while canonical has unrelated dirty state and bind a dirty snapshot to the lease; guarantee nexus_task_retry preserves task_id but creates a fresh attempt/action/idempotency identity; and prevent DIRECT_CANONICAL primary/codex requests from entering Assisted provider resolution or returning ASSIST_PROVIDER_NOT_REGISTERED. Preserve Direct dirty blocking, integration dirty blocking, human-only approval/integration, one serial Target budget, existing dirty files, and AUTO_CHAIN=false.

## Allowed files

- `tasks/lifecycle-concurrency-dispatch-corrective/INDEX.md`
- `tasks/lifecycle-concurrency-dispatch-corrective/00-lifecycle-concurrency-dispatch-corrective.md`
- `nexus/orchestrator/worktree_manager.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Verification commands

```bash
.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_worktree_manager.py -k 'dirty_controller or controller_snapshot'
.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'retry_task or terminal_retry'
.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py -k 'direct and primary or retry'
.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_unified_mcp_gateway.py
git diff --check
git diff --diff-filter=D --name-status
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

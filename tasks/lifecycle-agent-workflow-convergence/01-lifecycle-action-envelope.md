# Task Card: lifecycle-workflow-p1-action-envelope

artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: lifecycle-workflow-p1-action-envelope
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Implement the typed Task/Attempt/Action envelope and canonical request hash
without creating a second lifecycle or router.

## Dependencies

- `lifecycle-workflow-p0-authority-baseline` integrated.

## Allowed files

- `nexus/contracts/lifecycle_action.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/contracts/test_lifecycle_action.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Forbidden scope

- No new router, database, MCP server, or model worker.
- No approval, integration, push, or cleanup authority.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p1-pycache uv run pytest -q tests/contracts/test_lifecycle_action.py tests/nexus/orchestrator/test_unified_mcp_gateway.py
git diff --check
```

## Exit criteria

Round-trip schema, malformed identity, stale Task Card, wrong HEAD, duplicate
idempotency key, and request-hash mismatch are covered and fail closed.

## Block classification

- `HARD_BLOCK`: authority or schema conflict.
- `RECOVERABLE_BLOCK`: test/environment failure with changes preserved.

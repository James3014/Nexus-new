# Task Card: lifecycle-workflow-p6-approval-reconnect-drift

artifact_authority: current
owner: James Chen
status: PENDING
task_id: lifecycle-workflow-p6-approval-reconnect-drift
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Bind approval to full Candidate and runtime identity, detect tool/policy
definition drift, and recover reconnects without replaying mutations.

## Dependencies

- `lifecycle-workflow-p5-enforcement-permissions` integrated.

## Allowed files

- `scripts/ops/nexus_mcp_gateway_http.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/contracts/lifecycle_action.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p6-pycache uv run pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway_http.py tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
```

## Exit criteria

Restart/schema drift invalidates stale approval; reconnect lists and reconciles
uncertain actions; external registration remains one Gateway.

## Block classification

- `HARD_BLOCK`: approval binding or identity ownership is ambiguous.
- `RECOVERABLE_BLOCK`: restart/provider/test failure.

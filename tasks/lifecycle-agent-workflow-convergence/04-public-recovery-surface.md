# Task Card: lifecycle-workflow-p4-public-recovery-actions

artifact_authority: current
owner: James Chen
status: VERIFIED_PENDING_OWNER_REVIEW
task_id: lifecycle-workflow-p4-public-recovery-actions
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Expose typed list-actionable, reconcile, retry, resume, Candidate approve,
integrate, and dispose actions through the single public Gateway. Reuse the
existing self-hosted service methods.

## Dependencies

- `lifecycle-workflow-p3-fast-three-lane-dispatch` integrated.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/self_hosted_mcp.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_self_hosted_mcp.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p4-pycache uv run pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_self_hosted_mcp.py
git diff --check
```

## Exit criteria

Every non-terminal response has one `next_action`; retries reuse task_id;
pending Candidates are actionable without creating another task or Target.

## Verified evidence

- Gateway and HTTP recovery surface tests: `25 passed`, 0 failed, 0 skipped.
- Public tool manifest now contains 17 typed tools while retaining one Gateway.
- Recovery responses carry task/attempt/action identity, one next action,
  candidate binding, cleanup status, and uncertain-mutation state.
- Candidate approval, integration, and disposal remain separate service calls;
  the Gateway does not auto-approve or auto-integrate.

Promotion remains owner-gated; no Candidate approval, integration, push, or
cleanup was performed by the implementing Worker.

## Block classification

- `HARD_BLOCK`: public action would bypass approval/integration authority.
- `RECOVERABLE_BLOCK`: transport/test failure.

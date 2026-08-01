# Task Card: lifecycle-workflow-p7-acceptance-rollout

artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: lifecycle-workflow-p7-acceptance-rollout
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Run the lifecycle acceptance matrix, prove no unnecessary Target creation,
prove cleanup/recovery, and validate the GPT connector smoke path.

## Dependencies

- `lifecycle-workflow-p6-approval-reconnect-drift` integrated.

P6 is verified on canonical HEAD with generic tracked/Owner Inline approval
binding and exact focused suites. The Owner's continuing full-goal request
activates this acceptance implementation card; Cline live execution remains a
separate downstream provider gate.

## Allowed files

- `scripts/ops/nexus_mcp_gateway_acceptance.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`
- `tests/nexus/orchestrator/test_workflow_repair.py`
- `docs/arch/LIFECYCLE_AGENT_WORKFLOW_CONTRACT.md`

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p7-pycache uv run pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_unified_mcp_gateway_http.py tests/nexus/orchestrator/test_workflow_repair.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p7-pycache uv run python scripts/ops/nexus_mcp_gateway_acceptance.py
git diff --check
```

## Exit criteria

`active_targets=0`, `duplicate_commits=0`, all non-terminal tasks have one
next_action, protected main is unchanged, push is false, and one live
`nexus01` smoke covers read, Direct, and Candidate disposition.

## Block classification

- `HARD_BLOCK`: live claim ceiling cannot be proven or public MCP count differs.
- `RECOVERABLE_BLOCK`: provider/connector/environment failure with evidence retained.

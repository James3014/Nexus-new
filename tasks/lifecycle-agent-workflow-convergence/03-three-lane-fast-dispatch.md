# Task Card: lifecycle-workflow-p3-fast-three-lane-dispatch

artifact_authority: current
owner: James Chen
status: PENDING
task_id: lifecycle-workflow-p3-fast-three-lane-dispatch
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Use existing CapabilityPlanner authority to keep ordinary read/diagnostic and
small primary-agent work on canonical, use Assisted as proposal-first, and
reserve Isolated Target creation for risk/conflict/Candidate requirements.

## Dependencies

- `lifecycle-workflow-p2-durable-canonical-actions` integrated.

## Allowed files

- `nexus/engine/capability_planner.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p3-pycache uv run pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_unified_mcp_gateway_http.py
git diff --check
```

## Exit criteria

Read/status and bounded Direct fixture runs create zero Target; Assisted
defaults to proposal-only; no second route authority is introduced.

## Block classification

- `HARD_BLOCK`: route authority or lane contract conflict.
- `RECOVERABLE_BLOCK`: benchmark/environment issue.

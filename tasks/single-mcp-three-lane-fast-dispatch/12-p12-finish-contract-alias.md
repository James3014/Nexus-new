# Task Card P12: Direct Finish Contract Alias

## Identity

- task_id: `single-mcp-three-lane-p12-finish-contract-alias`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: IN_PROGRESS
- owner: James Chen
- objective: Let the public gateway finish a Direct task using the exact `base_sha` returned by `nexus_task_run`, while retaining the internal `controller_revision` compatibility alias.
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Allowed Files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Required Behavior

1. `nexus_task_finish` accepts `base_sha` as the public Direct completion field.
2. Existing `controller_revision` requests remain compatible.
3. The finish path still derives canonical roots, verifies exact scope, and never creates a Target or Candidate for Direct completion.

## Verification Commands

```bash
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway.py
```

## Exit Criteria

- New base-sha finish regression passes with existing gateway tests.
- Scoped commit and Direct receipt exist.
- External DevSpace and connector remain untouched.

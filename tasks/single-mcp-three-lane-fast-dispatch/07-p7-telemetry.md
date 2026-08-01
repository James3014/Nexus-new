# Task Card P7: Unified Gateway Phase Telemetry

## Identity

- task_id: `single-mcp-three-lane-p7-telemetry`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: IN_PROGRESS
- owner: James Chen
- objective: Attach bounded route, context, provider, patch-validation, commit, cleanup, and total wall-time telemetry to every gateway dispatch result.
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

1. Direct, Assisted, and Isolated dispatches return a stable telemetry object.
2. Provider time is separate from route decision, context build, patch validation, commit, cleanup, and total wall time.
3. A failed provider or rejected patch still returns telemetry and a fail-closed blocker.
4. Telemetry must not create a Target, lifecycle state, Candidate, or second routing authority.

## Verification Commands

```bash
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway.py
.venv/bin/python scripts/ops/nexus_mcp_gateway.py --self-test
```

## Exit Criteria

- Telemetry tests cover Direct and Assisted paths and provider/total separation.
- Failed Assisted paths remain fail-closed with telemetry.
- Scoped commit and Direct receipt exist.
- No external connector cutover is claimed by this card.

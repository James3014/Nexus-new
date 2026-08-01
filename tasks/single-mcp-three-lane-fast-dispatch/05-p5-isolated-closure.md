# Task Card P5: Unified Isolated Wait and Terminal Closure

## Identity

- task_id: `single-mcp-three-lane-p5-isolated-closure`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: IN_PROGRESS
- owner: James Chen
- objective: Expose bounded wait and lifecycle action envelopes through the single gateway while preserving Target cleanup, exact Candidate binding, owner approval, integration, and terminal disposition authority.
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

1. Expose one bounded `nexus_task_wait` tool with timeout and poll limits.
2. Return task status, attention, next action, recommended tool, and cleanup/candidate fields from existing service authority.
3. Never auto-approve, integrate, push, or dispose a Candidate.
4. Keep isolated Target root fixed at `nexus-runtime-targets`; retries retain task ID.

## Verification Commands

```bash
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway.py
.venv/bin/python scripts/ops/nexus_mcp_gateway.py --self-test
```

## Exit Criteria

- Wait and terminal action tests pass with FakeService forwarding.
- Existing Direct/Assisted routing remains green.
- Scoped commit and Direct receipt exist.

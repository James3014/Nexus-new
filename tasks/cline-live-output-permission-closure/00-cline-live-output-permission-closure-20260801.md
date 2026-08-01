# Task Card: cline-live-output-permission-closure-20260801

artifact_authority: current
task_id: `cline-live-output-permission-closure-20260801`
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

Prove real Cline GLM-5.2 stdout compatibility and bounded permission/cleanup behavior without canonical mutation.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/fixtures/cline/glm_52_real_stdout.ndjson`

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-cline-live-pycache .venv/bin/python -m pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

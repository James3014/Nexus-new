# Task Card: cline-live-output-parser-20260801

artifact_authority: current
task_id: `cline-live-output-parser-20260801`
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

Align the Cline JSON event-stream adapter with real stdout, extracting only the final assistant candidate and normalizing a schema-valid Nexus patch candidate while preserving fail-closed behavior and isolated no-canonical-mutation guarantees.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-cline-parser-pycache uv run pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

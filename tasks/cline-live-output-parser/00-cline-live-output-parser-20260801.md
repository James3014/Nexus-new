# Task Card: cline-live-output-parser-20260801

artifact_authority: current
task_id: `cline-live-output-parser-20260801`
owner: James Chen
status: INTEGRATED_PENDING_LIVE_REPLAY
candidate_commit: 026d4e12bc3517c3746137286fcafe057cbc196f
integration_commit: 90c8b9acd993e4db037f42a601cee2dbc042bdf3
live_cline_replay: NOT_YET_RUN
integration_note: Canonical HEAD contains the equivalent parser fix in commit 90c8b9a; candidate 026d4e12 is retained as provenance but is not an ancestor.
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

Canonical integration is recorded at `90c8b9acd`; live Cline stdout replay
remains outstanding. The detached parser worktree must be retained until its
candidate ancestry/unique-work and process-owner checks are satisfied.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

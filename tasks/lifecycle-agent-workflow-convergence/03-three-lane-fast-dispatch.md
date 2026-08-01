# Task Card: lifecycle-workflow-p3-fast-three-lane-dispatch

artifact_authority: current
owner: James Chen
status: VERIFIED_PENDING_OWNER_REVIEW
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

## Verified evidence

- Current HEAD `d596bb7f7948fa1cf1060a6fa04f637c1c74641b` was clean.
- Revision-bound manifest `/tmp/nexus-p3-gate.json` reported
  `nexus.fresh_suite_manifest.v1`, `PASS`, 23 passed, 0 failed, 0 skipped.
- The focused Gateway tests include the 10 Direct, 20 Assisted, and 10
  isolated routing soak cases, plus the single-`nexus/` regression and
  proposal-only default checks.

Promotion remains owner-gated; no approval, integration, push, or cleanup was
performed by the implementing Worker.

## Block classification

- `HARD_BLOCK`: route authority or lane contract conflict.
- `RECOVERABLE_BLOCK`: benchmark/environment issue.

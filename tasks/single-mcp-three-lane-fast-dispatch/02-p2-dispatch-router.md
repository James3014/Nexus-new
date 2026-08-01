# Task Card P2: CapabilityPlanner Dispatch Router

## Identity

- task_id: `single-mcp-three-lane-p2-dispatch-router`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: COMPLETED
- owner: James Chen
- objective: Add one minimal `nexus_task_run` gateway contract that derives canonical revisions/roots and records CapabilityPlanner-backed lane selection without exposing internal Target fields.
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Inputs and Dependencies

- `tasks/single-mcp-three-lane-fast-dispatch/INDEX.md`
- `tasks/single-mcp-three-lane-fast-dispatch/01-p1-gateway-foundation.md`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/engine/capability_planner.py`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `nexus/config/model_workforce.yaml`

## Allowed Files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `scripts/ops/nexus_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Required Behavior

1. Add `nexus_task_run` with only WHAT/WHY, bounded allowed files/verifiers, worker preference, and execution preference.
2. Derive current canonical HEAD and both lifecycle roots server-side.
3. Use `CapabilityPlanner` as the only route authority and return route, rationale, task ID, base revision, and next action.
4. Direct requests must use the existing Direct handoff; isolated requests must use existing governed lifecycle submission.
5. `ASSISTED_CANONICAL` must be fail-closed as not yet implemented until P3 lands; it must never silently allocate a Target.

Scope correction: the launcher self-test assertion is part of the P2 router
contract and is therefore explicitly included above.

## Verification Commands

```bash
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway.py
.venv/bin/python scripts/ops/nexus_mcp_gateway.py --self-test
.venv/bin/python -m scripts.engine.nexus_cli self-hosted list-actionable
```

## Exit Criteria

- The public gateway can route a bounded task without requiring controller/Target paths from GPT.
- CapabilityPlanner is cited as `route_authority` in every route envelope.
- Direct/isolated routing tests pass and assisted requests fail closed without side effects.
- Scoped commit and Direct receipt exist.

## Completion Evidence

- Runtime/scope commit: `940a6796d9e78174b2873f1e83e22d55e80aef82`
- Direct receipt: `f3550ff6ce91b8ff3a5361343612344e1b3b2907643d3dd610f1bfbb934235c1`
- Verification: 8 gateway tests passed; gateway self-test passed; `git diff --check` passed.
- Scope correction: launcher self-test was explicitly added to Allowed Files before completion.
- Side effects: `candidate_created=false`, `target_created=false`, `state_created=false`.

## Forbidden Scope

- No model invocation or patch application in P2.
- No new router authority, arbitrary provider fallback, or auto-approval.
- No external DevSpace changes or public connector cutover.

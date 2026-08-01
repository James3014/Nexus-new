# Task Card: lifecycle-workflow-p5-enforcement-permissions

artifact_authority: current
owner: James Chen
status: PENDING
task_id: lifecycle-workflow-p5-enforcement-permissions
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Add synchronous fail-closed action/state guards and bounded permission profiles.
EventBus remains observer-only and cannot approve or route.

## Dependencies

- `lifecycle-workflow-p4-public-recovery-actions` integrated.

## Allowed files

- `nexus/orchestrator/lifecycle_guards.py`
- `nexus/contracts/lifecycle_action.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/events/transport.py`
- `tests/nexus/orchestrator/test_lifecycle_guards.py`
- `tests/nexus/orchestrator/test_workflow_repair.py`
- `tests/core/test_event_bus.py`

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p5-pycache uv run pytest -q tests/nexus/orchestrator/test_lifecycle_guards.py tests/nexus/orchestrator/test_workflow_repair.py tests/core/test_event_bus.py
git diff --check
```

## Exit criteria

Wrong path, wrong HEAD, stale card, expired approval, and guard failure produce
zero mutation with structured reason codes.

## Block classification

- `HARD_BLOCK`: guard would become a second authority or fail open.
- `RECOVERABLE_BLOCK`: focused test/environment failure.

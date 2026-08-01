# Task Card: lifecycle-workflow-p5-enforcement-permissions

artifact_authority: current
owner: James Chen
status: COMPLETED_PENDING_OWNER_REVIEW
task_id: lifecycle-workflow-p5-enforcement-permissions
commit_required: true
candidate_required: false
execution_mode: OWNER_AUTHORIZED_CANONICAL
authority_exception: Owner continuation explicitly authorizes this bounded canonical implementation; it is not a Candidate/Isolated execution.
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Add synchronous fail-closed action/state guards and bounded permission profiles.
EventBus remains observer-only and cannot approve or route.

## Dependencies

- `lifecycle-workflow-p4-public-recovery-actions` remains owner-review pending;
  this card uses the explicit owner-authorized canonical implementation
  exception and must not claim P4 integration.

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

## Evidence and claim boundary

- `SYNCHRONOUS_GUARD_LAYER_IMPLEMENTED`: `nexus/orchestrator/lifecycle_guards.py`
  validates trusted tool-name manifest, expected HEAD, Task Card pair/hash,
  mutation domain, permission profile, and bounded paths before service state.
- `PERMISSION_PROFILE_STATIC_ENFORCEMENT_PASS`: mutation domains separate
  repository, lifecycle state, candidate ref, target, and integration scopes.
- `EVENTBUS_OBSERVER_FAILURE_TELEMETRY_PASS`: observer errors remain fail-open
  and are counted under a lock without changing route or approval state.
- Exact focused gate: `194 passed` across guard, workflow, Gateway, service,
  and EventBus suites; `git diff --check` passed.
- Execution authority: owner-authorized canonical implementation exception;
  this is not Candidate/Isolated execution and `candidate_required=false` is
  intentional for this card.
- P5 does not claim approval expiry, full definition drift, reconnect, GPT
  end-to-end, or acceptance rollout. Those remain P6/P7 gates.

## Block classification

- `HARD_BLOCK`: guard would become a second authority or fail open.
- `RECOVERABLE_BLOCK`: focused test/environment failure.

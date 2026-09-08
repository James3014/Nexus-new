# Task Card: transport-admission

artifact_authority: current
task_id: `transport-admission`
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

Owner authorizes goal-completion operations; repair verified canonical publication admission gap at 0d4487be7ed3362665be575f25ce5b89e107805c. Establish explicit closed mapping between concrete signed transport identity and inventoried execution route; do not assume equal strings mean identical concepts. Unknown/unregistered/UNKNOWN_BLOCKED route cannot dispatch even with otherwise exact Owner authorization. Revalidate admission before publish; preserve readback-only reconciliation without enabling redispatch, exact signature and internal passthrough. Injected test transports remain explicit safe fixtures, not default production approvals. Correct unsupported live interactive-gated inventory claims: missing live evidence is not enforced capability. No second Planner/router, no universal shell sandbox, no actual network/publication, no DevSpace edits. Luna implements RED/GREEN scoped immutable commit; coordinator independently verifies. No push/merge through this card.

## Allowed files

- `nexus/orchestrator/owner_representation.py`
- `nexus/security/owner_representation_transport_inventory.py`
- `tests/nexus/orchestrator/test_owner_representation.py`
- `docs/governance/OWNER_REPRESENTATION.md`

## Verification commands

```bash
python -m pytest -q tests/nexus/orchestrator/test_owner_representation.py tests/nexus/executors/test_cli_worker.py
python -m ruff check nexus/orchestrator/owner_representation.py nexus/security/owner_representation_transport_inventory.py tests/nexus/orchestrator/test_owner_representation.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.

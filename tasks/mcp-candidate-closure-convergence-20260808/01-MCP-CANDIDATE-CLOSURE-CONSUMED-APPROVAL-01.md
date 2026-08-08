# Task Card: MCP-CANDIDATE-CLOSURE-CONSUMED-APPROVAL-01

artifact_authority: current
task_id: `MCP-CANDIDATE-CLOSURE-CONSUMED-APPROVAL-01`
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

Repair the exact P1 closure blocker reproduced before canonical apply: a durable
`nexus.architecture_approval.v1` that was consumed inside its issued/expires
window is rejected later solely because wall-clock time has passed its expiry.
Validate an already-consumed approval at its immutable `consumed_at`, require
`issued_at <= consumed_at < expires_at`, reject future or malformed consume
timestamps, and preserve every existing task/attempt/commit/tree/findings-hash
binding. Do not accept an unconsumed or out-of-window approval, alter approval
identity, renew or fabricate approval, weaken RepositoryContractGate, bypass
the fresh `CANDIDATE_INTEGRATE` approval, or change Gateway, durable launcher,
OAuth, route, provider, workforce, or integration-manager behavior.

## Allowed files

- `nexus/orchestrator/lifecycle_guards.py`
- `tests/nexus/orchestrator/test_lifecycle_guards.py`
- `tests/nexus/orchestrator/test_repository_contract_gate.py`
- `tests/nexus/orchestrator/test_target_integration_authority_closure.py`

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_lifecycle_guards.py \
  tests/nexus/orchestrator/test_repository_contract_gate.py \
  tests/nexus/orchestrator/test_target_integration_authority_closure.py
git diff --check
```

## Required negative controls

- unconsumed expired approval remains blocked;
- consumed before issuance or at/after expiry remains blocked;
- future `consumed_at` remains blocked;
- task, attempt, candidate commit/tree, or authority findings hash drift remains blocked;
- validation never rewrites the persisted approval.

## Exit criteria

One scoped Candidate commit with exact tests green and independent primary-agent
review. The worker stops without integration, push, reload, or durable-state
mutation.

## Block classification

Any need to change files outside the allowed scope or weaken one-shot approval
identity is a HARD_BLOCK.

# Task Card: MCP-CANDIDATE-CLOSURE-REBIND-01

artifact_authority: current
task_id: `MCP-CANDIDATE-CLOSURE-REBIND-01`
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

Add the minimum pre-apply recovery to the existing typed Candidate integration
closure. A closure bound to an earlier canonical HEAD or runtime identity may
be rebound only by a fresh, exact, one-shot `CANDIDATE_INTEGRATE` approval while
the Candidate has not been merged or applied. Preserve immutable task, attempt,
candidate commit/tree/state, verified receipt, contract kind/hash, task-card
hash, external-acceptance receipt, integration branch, action type/scope, and
artifact identity. Only the current expected HEAD, current runtime identity,
fresh approval identity/timestamps, and newly derived preview/authorization may
change. Store every superseded closure, approval grant, preview, and
authorization in append-only history before replacing the current binding.

Exact replay of the same binding remains a zero-write duplicate, including
before environment-dependent probes. Semantic drift, stale approval, canonical
dirty/branch/head mismatch, or any prior merge/apply/integration result fails
closed. Binding and rebinding never integrate, approve, push, clean up, or
create a second lifecycle/integration authority.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_target_integration_authority_closure.py`

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_target_integration_authority_closure.py \
  tests/nexus/orchestrator/test_unified_mcp_gateway.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
```

## Required controls

- first bind succeeds and does not integrate;
- exact replay is duplicate and leaves history unchanged;
- fresh HEAD/runtime rebind preserves an exact snapshot in append-only history;
- fresh approval is consumed only after all validation passes;
- candidate/task/attempt/tree/state/receipt/contract/card/acceptance/branch/action drift fails with zero state mutation;
- rebind is rejected after any merge/apply/integration result;
- existing Gateway schema and dispatch remain unchanged and bind-only.

## Forbidden scope

Do not change Gateway schema, add a public tool, touch
`mcp_gateway_durable.py`, OAuth, CapabilityPlanner, routing, workforce,
providers, RepositoryContractGate, integration manager, lifecycle JSON, or
canonical apply/push/cleanup behavior. Do not delete or rewrite prior closure
evidence.

## Exit criteria

One scoped Candidate commit, exact tests green, clean worktree, and independent
primary-agent review. Worker stops without integration, reload, push, or
durable-state mutation.

## Block classification

Any need to widen the public schema, alter immutable identity, or discard prior
evidence is a HARD_BLOCK.

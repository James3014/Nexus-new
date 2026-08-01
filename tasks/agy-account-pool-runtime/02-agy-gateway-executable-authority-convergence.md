---
artifact_authority: current
owner: James Chen
status: PENDING
task_id: agy-gateway-executable-authority-convergence
campaign_id: agy-account-pool-runtime
depends_on: agy-account-pool-real-manager-runtime-closure
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
AUTO_CHAIN: false
---

# Task Card: AGY Gateway Executable Authority Convergence

## Objective

Make Nexus Gateway provider preflight and the self-hosted AgyWorkerAdapter
resolve the same real AGY executable authority, and permit an explicitly
provider-scoped AGY account-pool dispatch without changing route authority or
enabling the account pool for unrelated providers by default.

## Allowed files

- `nexus/services/unified_runtime.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/executors/worker_registry.py`
- `tests/services/test_unified_runtime.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/executors/test_worker_contract.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Forbidden scope

- route authority, CapabilityPlanner, HybridRouteDecision, or workforce policy
- provider/model downgrade or alternate router
- manager credentials, account identities, raw HOME, or raw provider output
- global feature enablement for non-AGY providers
- changing Card 01 files outside its existing scoped behavior
- protected-main merge, push, ref deletion, or self-approval

## Required behavior

- `resolve_registered_online_cli_spec("agy")` is the single executable
  resolver used by Gateway preflight and AgyWorkerAdapter.
- `NEXUS_AGY_BIN` and `NEXUS_AGY_EXECUTABLE` may be aliases, but a configured
  executable must resolve to the same file identity and fail closed on drift.
- AGY external authorization and account-pool enablement are provider-scoped
  runtime gates; unrelated provider dispatch remains unchanged.
- Explicit AGY dispatch uses the installed manager runtime and preserves the
  account alias hash / rotation receipt contract from Card 01.
- No route or public claim is upgraded without a real bounded dispatch receipt.

## Verification

- focused resolver, Gateway, worker, and service tests
- compileall for all touched modules
- `git diff --check`
- launchd environment contains only the AGY-scoped aliases/gates
- one bounded Gateway AGY dispatch with `apply=false`, sanitized account
  identity, and no canonical mutation

## Claim ceiling

Allowed: `SHARED_AGY_EXECUTABLE_RESOLVER`,
`AGY_PROVIDER_SCOPED_RUNTIME_AUTH`, `ACCOUNT_POOL_DISPATCH_ATTEMPTED`.

Forbidden until live success: `AGY_LIVE_MODEL_EXECUTION_PASS`,
`PRODUCTION_READY`, `PUBLIC_CLAIM_ALLOWED`, merge, push, or self-approval.

## Stop and block

Preserve the candidate on executable drift, credential leakage, unexpected
route change, canonical mutation, or provider authentication/model failure.
Classify external provider rejection as `RECOVERABLE_BLOCK`.

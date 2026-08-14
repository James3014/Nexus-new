---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: github-issue-190-account-lease-contract
campaign_id: github-issue-187-shared-account-pools-20260812
source_issue: https://github.com/James3014/Nexus-new/issues/190
baseline_main: bc16cbf2bf00377a4521e3eab233175112d0c963
AUTO_CHAIN: false
worker_preference: agy / gemini-3.6-flash-high
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
claim_ceiling: request_scoped_external_account_lease_contract_implemented_and_merged
completion_disposition: DONE_NO_FOLLOW_UP
merged_pr: 201
merged_main: 21add665679acaa57a795296dfef2f5b4e49af27
---

# Task Card: Request-scoped external account lease contract

## Objective

Implement the smallest provider-neutral account-pool contract needed for Agy and Grok to serve concurrent Codex/Nexus consumers safely after a provider is already selected.

The contract SHALL provide request-scoped leases, non-secret account identity, independent release/rotation, structured account failure classification, and fail-closed exhaustion. It SHALL NOT become a route/model/provider selector.

## Inputs and authority

- Campaign Issue #187.
- Ready implementation Issue #190.
- Collaboration baseline `Nexus-new/main@bc16cbf2bf00377a4521e3eab233175112d0c963`.
- Root `AGENTS.md` and `docs/agents/TASK_EXECUTION_CONTRACT.md`.
- `CapabilityPlanner` remains sole route/capability selection authority.

## Allowed files

Implementation:
- `nexus/services/external_account_pool.py`
- `tests/services/test_external_account_pool.py`

Governance files:
- `tasks/github-issue-187-shared-account-pools-20260812/INDEX.md`
- `tasks/github-issue-187-shared-account-pools-20260812/01-account-lease-contract.md`

Maximum changed files for this Issue Candidate: 4.

## Required behavior

- One `AccountLease` binds one consumer/request to one account inside one already-selected provider.
- Public lease state exposes `lease_id`, provider, consumer identity, a non-secret account alias hash, and immutable non-secret execution binding data only.
- The neutral layer SHALL NOT import Agy, Grok, codex-router, OAuth implementations, or parse provider-specific raw HTTP/CLI error strings.
- Provider adapters classify raw failures before calling the neutral pool.
- Rotation-eligible failure classes: auth/session invalid, token expired, token refresh failed, quota exhausted, provider rate limited, account unavailable, account disabled.
- Non-rotation classes: model/task error, syntax/implementation error, verifier failure, cancellation, timeout, permission/scope failure, unknown.
- Releasing or rotating one lease SHALL NOT mutate unrelated active leases.
- An eligible failure SHALL mark only the failed account unavailable, release only that lease, and reacquire for the same consumer from another usable account.
- Pool exhaustion SHALL fail closed with a typed exception.
- No synthetic/default account may be created for an unknown or empty provider pool.

## Forbidden scope

- No changes to `CapabilityPlanner`, `HybridRouteDecision`, workforce routing or model selection.
- No changes to existing Agy manager behavior in this card.
- No Grok OAuth/account implementation.
- No Codex/codex-router or Agy MCP bridge integration.
- No credentials, real aliases, OAuth/token material, machine-local account state, `.key`/`.crt`, or generated runtime artifacts.
- No approval, integration, merge, release, runtime activation, or production/public claim.

## Verification

Run and record:

1. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/services/test_external_account_pool.py`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/services/test_agy_account_pool.py tests/nexus/executors/test_worker_contract.py -k 'agy or account_pool'`
3. `python3 -m compileall -q nexus/services/external_account_pool.py tests/services/test_external_account_pool.py`
4. `git diff --check`
5. Exact changed/deleted/out-of-scope path audit.

The full `test_worker_contract.py` suite may additionally be observed, but a provider-binary preflight failure unrelated to this diff must be reported separately rather than rewritten as implementation evidence.

## Required evidence

- Exact base/head/tree identity.
- Complete changed-file inventory.
- Focused contract tests including concurrent bindings, independent release/rotation, positive/negative failure taxonomy, immutable execution env, unknown/empty pool, and exhaustion.
- Existing Agy account-pool/worker regression evidence.
- Agy worker output remains Candidate-only and receives no approval/integration authority.

## Exit / next gate

A passing implementation ends at `request_scoped_external_account_lease_contract_candidate_only` and requires independent acceptance before merge.

Only accepted merge plus post-merge readback may unblock #191 and #192. `AUTO_CHAIN=false`; do not start either downstream Issue from this card.

## Completion reconciliation — 2026-08-14

- Issue #190: `DONE_NO_FOLLOW_UP`; implementation merged through PR #201.
- Final synchronized integration head before merge: `eeafe6869e71614da7f2fab6201d924e44033c21`.
- PR #201 merge commit: `21add665679acaa57a795296dfef2f5b4e49af27`; verified ancestor of current `nexus-new/main` `eb668fb76f0c30d8f025db42cdb8e320d556c037`.
- Exact merged scope: 4 files / 0 deletions (`nexus/services/external_account_pool.py`, `tests/services/test_external_account_pool.py`, this card, campaign `INDEX.md`).
- Current-main focused evidence rerun: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/services/test_external_account_pool.py` → 22 passed.
- Durable claim ceiling: `request_scoped_external_account_lease_contract_implemented_and_merged` only. No provider/account/runtime/Codex/Agy/Grok production claim is inherited.

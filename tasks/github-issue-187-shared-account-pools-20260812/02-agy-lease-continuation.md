---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-191-agy-lease-continuation
campaign_id: github-issue-187-shared-account-pools-20260812
source_issue: https://github.com/James3014/Nexus-new/issues/191
baseline_main: 37526fc9705cf984b0b2fd9f373460b3c98d7391
AUTO_CHAIN: false
worker_preference: agy / gemini-3.6-flash-high
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
claim_ceiling: agy_request_scoped_lease_continuation_candidate_only
---

# Task Card: Agy request-scoped lease failover and continuation

## Objective

Adapt the existing Agy account-pool and worker path to the merged provider-neutral `AccountLease` contract without replacing `agy-cli-manager` as the Agy provider-state authority.

The bounded result SHALL bind each Agy execution to an immutable request-scoped account environment, preserve current auth/quota retry budgets, and start a fresh Agy child session with a bounded continuation handoff after an eligible account failure. It SHALL NOT assume an Agy conversation ID is portable across account identities.

## Inputs and authority

- Campaign Issue #187.
- Ready implementation Issue #191.
- Completed predecessor #190 / PR #201, merged at `21add665679acaa57a795296dfef2f5b4e49af27`.
- Collaboration baseline `Nexus-new/main@37526fc9705cf984b0b2fd9f373460b3c98d7391`.
- Root `AGENTS.md` and `docs/agents/TASK_EXECUTION_CONTRACT.md`.
- `CapabilityPlanner` remains sole route/capability selection authority.

## Candidate status — 2026-08-14 (updated after PR #239 merge)

- PR #239 merged as `nexus-new/main@37526fc9705cf984b0b2fd9f373460b3c98d7391`; PR #237 rebound onto that exact main with current head `7e216d8769a07589f80615f3f2470abaddde0a62` and exact scope:
  - `nexus/services/agy_account_pool.py`
  - `nexus/executors/worker_registry.py`
  - `tests/services/test_agy_account_pool.py`
  - `tests/nexus/executors/test_worker_contract.py`
- Exact-head required checks and exact-base impact reached terminal success; focused suite 94 passed; candidate independently accepted `MERGE_SLOT_ONLY`. Only the exact Owner merge slot remains; the candidate is not yet merged.
- This card does not authorize new #191 implementation and does not widen PR #237 scope; no readiness/approval/integration/production claim.

## Allowed files

Implementation:
- `nexus/services/agy_account_pool.py`
- `nexus/executors/worker_registry.py`
- `tests/services/test_agy_account_pool.py`
- `tests/nexus/executors/test_worker_contract.py`

Governance files:
- `tasks/github-issue-187-shared-account-pools-20260812/INDEX.md`
- `tasks/github-issue-187-shared-account-pools-20260812/01-account-lease-contract.md`
- `tasks/github-issue-187-shared-account-pools-20260812/02-agy-lease-continuation.md`

Maximum changed files for this Issue Candidate: 7.

Any need to modify `nexus/services/external_account_pool.py`, `nexus/executors/worker_contract.py`, provider-manager package files, route/planner/workforce policy, or another source/test path is a contract delta and requires coordinator review before mutation.

## Required behavior

### 1. Agy lease binding

- Reuse the merged `AccountLease` / `AccountFailureKind` semantics; do not create a second neutral lease contract.
- The Agy provider wrapper SHALL expose request-scoped `acquire`, `release`, and eligible-failure rotation/reporting behavior compatible with the neutral contract.
- Public lease state exposes only provider, consumer/request identity, `lease_id`, non-secret alias hash, and immutable execution environment.
- Raw account aliases remain provider-internal and SHALL NOT enter receipts, prompts, exceptions, repository files, or logs added by this change.
- For the real manager, lease `HOME` SHALL point to the selected provider-owned account snapshot home (`manager_root/accounts/<provider-internal-alias>`), not the mutable manager `live-home` projection.
- A change to manager global active/live projection SHALL NOT mutate an already-issued lease's `execution_env`.
- The wrapper may call existing manager status/ensure/switch/rotation commands and read existing health/cooldown state, but SHALL NOT create a second persisted Agy health/quota/cooldown policy.
- Existing manager lock semantics remain authoritative for manager-state mutation.

### 2. Provider-specific failure classification

- `AgyWorkerAdapter` classifies raw Agy CLI failures into the merged structured account failure taxonomy before asking the pool to rotate.
- Eligible account/provider failures include auth/session invalid, token expiry/refresh failure where observable, quota exhaustion, provider rate limit, account unavailable/disabled.
- Timeout, syntax/model/task failure, verifier failure, cancellation, permission/scope error, and unknown failures SHALL NOT rotate accounts solely because execution failed.
- Keep current maximum-provider-call and shared wall-time budgets fail closed; no unbounded account cycling.

### 3. Fresh-session continuation

- The first provider attempt receives the original task prompt unchanged apart from existing launcher behavior.
- After an eligible failure changes the account binding, the next Agy call starts a fresh child session (`--new-project` remains) and receives a bounded continuation handoff.
- The continuation handoff carries only what the new child needs to safely continue: task id, attempt number, prior/new non-secret alias hashes, structured failure kind, same-worktree instruction, original bounded task instruction, and an instruction to inspect current worktree/diff/tests before continuing.
- The handoff SHALL NOT claim cross-account conversation portability, pass an old conversation ID, include raw account aliases, copy auth material, or replay raw stdout/stderr/provider error bodies.
- Partial filesystem state in the same isolated worktree is authoritative; the new child must continue from that physical state rather than assuming prior conversational memory.

### 4. Worker receipts and cleanup

- Preserve existing `WorkerExecutionReceipt.account_alias_hash` and `provider_attempt_count` semantics; final receipt identifies the final bound account only by alias hash and records bounded provider-attempt lineage by count.
- Release the final request lease on terminal success/failure without invalidating unrelated leases.
- Pool exhaustion fails closed and SHALL NOT synthesize a default account.
- Pool-disabled Agy behavior remains backward compatible.

### 5. Concurrency claim boundary

- Tests SHALL prove two in-process consumers can hold immutable Agy lease bindings concurrently and that rotating one consumer does not rewrite the other's execution environment.
- This card does NOT claim cross-process Codex+Nexus lease fencing, production credential orchestration, or final machine-wide concurrency closure; those remain downstream campaign gates.

## Forbidden scope

- No new Router, Planner, RouteMode, topology selector, execution-topology string, or model-selection branch.
- No change to `CapabilityPlanner` / `HybridRouteDecision` authority.
- No changes to the merged provider-neutral lease contract in this card.
- No edits to installed `agy-cli-manager` vendor code or machine credential/profile files.
- No credential provisioning, login/logout, OAuth/session mutation, account rename, or real-alias persistence.
- No Grok implementation.
- No Codex/codex-router or Agy MCP bridge integration.
- No test weakening, skip/xfail addition, assertion deletion, or provider-error swallowing.
- No approval, integration, merge, release, runtime activation, production-ready, or public claims by the worker.

## Verification

Run and record exactly:

1. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/services/test_agy_account_pool.py`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/nexus/executors/test_worker_contract.py -k 'agy or account_pool'`
3. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/services/test_external_account_pool.py tests/services/test_agy_account_pool.py`
4. `python3 -m compileall -q nexus/services/agy_account_pool.py nexus/executors/worker_registry.py tests/services/test_agy_account_pool.py tests/nexus/executors/test_worker_contract.py`
5. `git diff --check`
6. Exact changed/deleted/out-of-scope path audit.

Required focused witnesses include:

- lease environment uses provider-owned account snapshot HOME rather than mutable live-home;
- two concurrent consumer bindings remain independent;
- eligible auth/quota/rate-limit failure rotates only the failed request binding;
- non-account failure and timeout do not rotate;
- continuation handoff is injected only after an eligible account change and contains no raw alias/conversation/auth/error-body data;
- provider-call and wall-time budgets remain bounded;
- exhaustion fails closed;
- pool-disabled behavior remains unchanged;
- existing real-manager smoke/status tests remain non-secret and green when the physical manager is available.

## Required evidence

- Exact base/head/tree identity and Task Card blob/hash.
- Fresh Workforce Admission for the exact worker/role/scope before delegated mutation, plus provider preflight identity.
- Complete changed-file inventory and deletion audit.
- Focused lease/continuation tests and existing Agy regression evidence.
- Exact Agy worker/provider attempt count and non-secret account hash evidence only.
- Independent review must inspect the exact Candidate diff and rerun focused tests; worker self-review is not acceptance.

## Block conditions

Stop without widening scope on any of:

- `WORKFORCE_ADMISSION_UNAVAILABLE` or admission `BLOCK/ESCALATE` for the requested role;
- provider preflight no longer proves the requested model/identity;
- current `main` or this issue branch drifts before mutation;
- overlapping active Candidate/PR appears;
- implementation requires changing the neutral lease contract or worker receipt schema;
- per-account snapshot HOME cannot be proven safe for direct Agy execution;
- credentials/private keys/OAuth material would enter repository state;
- required verifier command cannot be run as written.

## Exit / next gate

A passing implementation ends at `agy_request_scoped_lease_continuation_candidate_only` and requires independent exact-head acceptance before merge.

Only accepted merge plus post-merge readback/reconciliation may unblock Issue #192. `AUTO_CHAIN=false`; do not begin Grok implementation from this card.

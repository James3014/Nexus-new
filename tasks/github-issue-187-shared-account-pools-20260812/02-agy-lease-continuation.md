---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-191-agy-lease-continuation
campaign_id: github-issue-187-shared-account-pools-20260812
source_issue: https://github.com/James3014/Nexus-new/issues/191
source_campaign_issue: https://github.com/James3014/Nexus-new/issues/187
baseline_main: 21add665679acaa57a795296dfef2f5b4e49af27
upstream_contract: github-issue-190-account-lease-contract
upstream_merge: 21add665679acaa57a795296dfef2f5b4e49af27
AUTO_CHAIN: false
worker_preference: agy / gemini-3.6-flash-high
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
claim_ceiling: agy_request_lease_continuation_candidate_only
---

# Task Card: Agy request-scoped lease + fresh-session continuation

## Objective

Adapt Nexus Agy execution to the request-scoped account lease contract merged by Issue #190 while preserving `agy-cli-manager` as the machine-local Agy account/profile and health-metadata implementation.

Agy execution SHALL bind each in-flight consumer to a provider-specific account HOME without changing the vendor manager's machine-global active/live profile. An eligible account failure SHALL mark the exact failed account bad/cooldown, reacquire another request lease, start a fresh Agy subprocess/session, and continue from the same worktree with a bounded continuation prompt.

## Start-state evidence

Current collaboration source: `Nexus-new/main@21add665679acaa57a795296dfef2f5b4e49af27`.

Verified current source:
- `nexus/services/external_account_pool.py` provides `AccountLease`, `InternalAccountRecord`, `ExternalAccountPool`, `AccountFailureKind`, independent lease release/rotation, and fail-closed exhaustion.
- `nexus/services/agy_account_pool.py` still exposes the legacy active-account seam and invokes `ensure-active`, `status`, and `rotate-after-failure` for the real manager.
- `AgyWorkerAdapter` still selects the current active account for each attempt, uses the global active HOME, and calls `rotate_account()` after auth/quota failures.
- `WorkerExecutionReceipt` currently records only final `account_alias_hash` and `provider_attempt_count` for account-related evidence.

Verified machine-local vendor behavior (implementation evidence only; credentials are not repository inputs):
- saved Agy account profiles live independently under the manager root `accounts/<name>` and each saved home contains its own `.gemini` profile;
- vendor `switch`/`rotate-after-failure` copy a selected profile through global runtime/live directories and therefore SHALL NOT be used for request-scoped execution;
- vendor CLI publicly exposes exact-account `mark-bad <name> --reason ... --cooldown-minutes ...`;
- vendor `status --json` exposes enabled/status/derived health metadata and does not require exposing credentials to Nexus receipts.

The local Git collaboration ref is stale relative to this Task Card baseline. Any Agy CLI proposal generated from the local machine must treat the exact GitHub source snapshots supplied in its prompt as source authority and must not infer current source from the stale checkout.

## Allowed files

Implementation:
- `nexus/services/agy_account_pool.py`
- `nexus/executors/worker_registry.py`
- `nexus/executors/worker_contract.py`

Tests:
- `tests/services/test_agy_account_pool.py`
- `tests/nexus/executors/test_worker_contract.py`

Governance:
- `tasks/github-issue-187-shared-account-pools-20260812/INDEX.md`
- `tasks/github-issue-187-shared-account-pools-20260812/01-account-lease-contract.md`
- `tasks/github-issue-187-shared-account-pools-20260812/02-agy-lease-continuation.md`

Maximum changed files: 8.

## Required behavior

### Agy provider lease adapter

- Reuse the merged provider-neutral `ExternalAccountPool`; do not implement a second lease engine.
- For the real manager, build lease candidates from `status --json` and the manager root's saved account homes, not `live_dir`.
- Filter out disabled/cooldown/auth-missing/auth-expired accounts using vendor status/health metadata. Do not fabricate a default account when no real account is usable.
- Keep raw account names private inside the Agy provider adapter. Public leases/receipts expose only existing non-secret alias hashes.
- `acquire_lease(consumer_id)` returns a request-scoped lease whose execution environment uses that saved account HOME and strips sensitive Google/Gemini API-key variables.
- `release_lease(lease)` releases only that binding.
- On a rotation-eligible failure, map the exact lease back to its private account identity, call vendor `mark-bad` for that exact account, report the structured `AccountFailureKind` to the neutral pool, and return a replacement lease. Do not call vendor `switch`, `switch-next`, `rotate`, `apply-active`, or `rotate-after-failure` for the request path.
- Preserve the existing in-memory test/fallback account mode through the same lease-facing behavior.

### Agy worker retry semantics

- When pool support is enabled/injected, prefer the request-scoped lease API. A compatibility fallback may remain only for legacy injected test doubles; the real `AgyAccountPoolManager` path must use leases.
- Convert raw Agy CLI auth/quota/rate-limit signals into the structured account failure taxonomy before calling the pool.
- Timeout, semantic/task, syntax/implementation, verifier, cancellation, and permission/scope failures do not rotate accounts merely because execution failed.
- All attempts remain bounded by the existing provider-call and shared wall-time budgets.
- Each attempt uses the exact lease's isolated execution environment.

### Fresh-session continuation

After a rotation-eligible failure and successful lease replacement:
- start a new Agy subprocess/session; do not use `--continue` or reuse a prior conversation ID;
- reuse the same target worktree;
- send a bounded continuation prompt that states this is a fresh session after provider/account failover, tells the worker to inspect and preserve existing worktree changes, restates the original task, and includes only non-secret attempt metadata (attempt number, prior account hash, prior stdout/stderr hashes or equivalent evidence IDs, and structured failure kind);
- do not copy raw prior conversation text, credentials, real account names, tokens, or human-review bundle files into the continuation.

### Receipt lineage

Extend `WorkerExecutionReceipt` with backward-compatible optional non-secret account failover lineage sufficient to recover:
- ordered account alias hashes used by provider attempts;
- structured account failure kinds that caused rotations.

Existing `account_alias_hash` remains the final/last account identity and `provider_attempt_count` remains the actual provider attempt count. New lineage fields must normalize safely after JSON/state round trips and default empty for non-account providers.

## Acceptance criteria

1. Two simulated Agy consumers can hold independent leases; releasing or rotating one does not change the other's lease/account hash/HOME.
2. Real-manager fixture proves lease HOME is `manager_root/accounts/<account>` and not the global `live_dir` home.
3. Exact-account failure fixture proves `mark-bad` targets only the failed raw account and that no global switch/rotate command is invoked.
4. Eligible quota/auth/rate-limit failure retries with a different lease within the existing provider-call budget.
5. Timeout and syntax/model/task failures do not rotate.
6. The retry subprocess uses the same worktree, a fresh Agy session, a different account HOME, and a bounded continuation prompt with no raw account identity or credential.
7. Receipt lineage records only non-secret account hashes + structured failure kinds and accurately represents A->B retry order.
8. Existing Agy pool/worker behavior with account pooling disabled remains compatible.
9. Existing relevant Agy worker/account-pool tests remain green; exact-base GitHub CI introduces no new regression.
10. `git diff --check`, Ruff/format, compile/static checks, exact scope/deletion audit, and credential-secret scan pass.

## Required verification

At minimum:

1. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/services/test_agy_account_pool.py`
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/nexus/executors/test_worker_contract.py -k 'agy or account_pool'`
3. `python3 -m compileall -q nexus/services/agy_account_pool.py nexus/executors/worker_registry.py nexus/executors/worker_contract.py tests/services/test_agy_account_pool.py tests/nexus/executors/test_worker_contract.py`
4. repository Ruff check/format for changed Python paths
5. `git diff --check`
6. exact changed/deleted/out-of-scope file audit
7. GitHub exact-base impact + trusted verifier gates before merge.

A live credential canary is not required to accept this repository Candidate and must not be performed from this Task Card. Live provider/cross-consumer validation remains downstream campaign work.

## Forbidden scope

- No edits to the installed `agy-cli-manager` package.
- No global profile switching for per-request execution.
- No Grok implementation.
- No Codex/codex-router/Agy-MCP bridge integration.
- No `CapabilityPlanner`, `HybridRouteDecision`, workforce policy/model selection, route authority, approval, merge, release, or production changes.
- No use or commit of real account names/emails, OAuth tokens, subject IDs, account profile bytes, `.key`/`.crt`, or machine runtime state.
- Do not repurpose `nexus/core/handoff_bundle.py`; it remains the HUMAN_REVIEW handoff authority.

## Evidence / exit

Agy CLI is the preferred bounded implementation proposer, but its output is Candidate-only and cannot self-approve or self-integrate.

A passing Candidate ends at `agy_request_lease_continuation_candidate_only` and requires independent acceptance against the exact commit/tree/diff plus current required checks. Only protected merge + post-merge readback may close #191 and select the next campaign frontier.

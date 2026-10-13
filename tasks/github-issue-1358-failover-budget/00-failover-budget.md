# Issue 1358 — Agy Failover Budget Separation: Pre-Effect / Account Failures Must Not Consume Work Budget

- task_id: `github-issue-1358-failover-budget`
- campaign_id: `github-issue-1358-failover-budget`
- status: `CANDIDATE`
- owner: `James Chen (James3014)`
- coordinator: `Antigravity Engineer`
- issue: `https://github.com/James3014/Nexus-new/issues/1358`
- durable_marker: `AGY_FAILOVER_BUDGET_SEPARATION_ENFORCED`
- AUTO_CHAIN: `false`

## Objective

Separate account-selection / provider-failover failures from the logical model-work budget (`work_failures` / `max_calls`).
Ensure that:
1. An explicit predicate / set distinguishes account-selection / failover failures (`ACCOUNT_FAILOVER_FAILURES`, `is_account_failover_failure`) from true model-work failures.
2. Rotation-eligible account failures occurring before meaningful model work (e.g. `ACCOUNT_UNAVAILABLE`, `AUTH_OR_SESSION_INVALID`, `TOKEN_EXPIRED`, `TOKEN_REFRESH_FAILED`, `ACCOUNT_DISABLED`, `RATE_LIMITED`, and `QUOTA_EXHAUSTED`) do not consume `work_failures` or burn the user's `max_calls` budget.
3. Healthy replacement accounts in the pool are attempted with the full model-work budget rather than prematurely failing with exhausted calls.
4. Bounded rotation ceilings (`max_failovers`, `ACCOUNT_FAILOVER_LIMIT`) and pool exhaustion semantics (`AgyAccountPoolExhaustedError`, `pool_exhausted`) remain authoritative, preventing unbounded loops.
5. True model-work failures (such as `TIMEOUT`, `MODEL_OR_TASK_ERROR`) and syntax/implementation errors consume the model-work budget or exit immediately as required by existing failure taxonomy.
6. Post-effect failures and `OUTCOME_UNKNOWN` semantics are strictly preserved; no account rotation is permitted after repository effects have been observed.
7. Terminal telemetry distinguishes between failover ceiling (`ACCOUNT_FAILOVER_LIMIT`), pool exhaustion (`pool_exhausted`), and real model-work exhaustion (`failed` with model-work failure kind).

## Allowed Files

- `nexus/services/external_account_pool.py`
- `scripts/ops/nexus-agy-dispatch`
- `tests/services/test_account_concurrency.py`
- `tasks/github-issue-1358-failover-budget/00-failover-budget.md`
- `tasks/github-issue-1358-failover-budget/INDEX.md`

## Acceptance Criteria

1. `ACCOUNT_FAILOVER_FAILURES` and `is_account_failover_failure` are defined in `nexus/services/external_account_pool.py` covering canonical provider/account failures: `AUTH_OR_SESSION_INVALID`, `TOKEN_EXPIRED`, `TOKEN_REFRESH_FAILED`, `QUOTA_EXHAUSTED`, `RATE_LIMITED`, `ACCOUNT_UNAVAILABLE`, `ACCOUNT_DISABLED`.
2. In `scripts/ops/nexus-agy-dispatch`, `work_failures` is only incremented when `not is_account_failover_failure(kind)`; account-level failures do not consume `work_failures`.
3. An `ACCOUNT_UNAVAILABLE` (e.g. 503) failure on account A with `max_calls=1` rotates cleanly to healthy account B and completes successfully (`exit 0`), reproducing and fixing `AGY_FAILOVER_BUDGET_G0_ACCOUNT_UNAVAILABLE_RED_FIXTURE`.
4. Auth/session invalid and rate limited failures also perform bounded rotation without consuming the model-work budget.
5. `MODEL_OR_TASK_ERROR` and syntax/implementation errors are preserved as non-rotation failures and terminate immediately.
6. When all accounts in the pool fail with account-level errors, dispatch terminates cleanly with `status="pool_exhausted"` (exit 75) without infinite looping.
7. When failover limit is reached across many accounts, dispatch terminates with `failure_kind="ACCOUNT_FAILOVER_LIMIT"` (exit 75).
8. Full deterministic test suite, Ruff linting/formatting, and git diff checks pass completely.

## Claim Ceiling

Source candidate and verified test suite only. No unilateral acceptance, merge, runtime activation, or release authority.

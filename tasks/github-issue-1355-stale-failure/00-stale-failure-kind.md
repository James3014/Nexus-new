# Task Contract: Issue #1355 Stale failure_kind after rotation success

## Problem Statement
When an operation encounters an initial recoverable failure (e.g. `PROVIDER_QUOTA_EXHAUSTED_PRE_EFFECT`), the dispatcher rotates accounts and starts a subsequent attempt. If the subsequent attempt succeeds (`COMPLETED / exit 0`), the live operation state previously retained `failure_kind=QUOTA_EXHAUSTED`, resulting in an internally inconsistent terminal record (`status=COMPLETED, exit_code=0, failure_kind=QUOTA_EXHAUSTED`).

## Acceptance Criteria
1. At each new `EXECUTING` attempt, the live operation record explicitly projects `failure_kind=None` to clear recovered failures.
2. If the rotated attempt succeeds, terminal state has `failure_kind=None` and `status=COMPLETED`.
3. If the rotated attempt fails, the new failure kind overwrites `failure_kind` before terminalization.
4. Earlier failure events remain safely recorded in the operation journal history.
5. All regression tests pass deterministically.

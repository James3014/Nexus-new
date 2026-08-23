# TASK-522-001 — Rebind workforce dispatch envelope on formal retry

```yaml
task_id: TASK-522-001
issue: 522
repository: James3014/Nexus-new
status: ACTIVE
auto_chain: false
claim_mode: MANUAL_DISPATCH
base_main: 7ad264e1c12a2b4d3896b4cdeec68688acf034f7
base_tree: b9057f8ef736fb6d3cd30da983f33f5f61fb86e9
work_branch: codex/issue-522-retry-dispatch-envelope-rebind
claim_ceiling: LIFECYCLE_RETRY_DISPATCH_ENVELOPE_REBIND_CLOSED_AT_SOURCE_TEST_CANDIDATE
```

## Objective

Make every lawful formal retry of a workforce-bound durable request carry a
fresh canonical dispatch envelope derived from its fresh attempt identity,
while retaining fail-closed rejection of stale, malformed, tampered, or
cross-task envelopes before worker/provider invocation.

## Authority

Issue #522 and this committed card authorize one source/test Candidate on the
named issue branch only. They do not authorize approval, integration, protected
merge, runtime activation, provider execution during governance, downstream
#517 completion, release, production, or public claims.

The task is worker-neutral until a fresh machine Workforce Admission returns
exact `ALLOW` for the selected worker/provider/model/role/context/scope and
the provider transport is independently runnable. Implementer output is never
its own acceptance evidence. `AUTO_CHAIN=false`.

## Root cause

`_retry_request()` mints fresh `attempt_id`, `action_id`, and
`idempotency_key`. The REPAIRABLE path rebuilds
`canonical_dispatch_envelope`; the generic non-REPAIRABLE path can retain the
old attempt-bound envelope. `submit_task()` correctly rebuilds the expected
envelope for the fresh attempt and rejects the stale one with
`WORKFORCE_DISPATCH_ENVELOPE_MISMATCH`.

## Exact mutation scope

Allowed paths, maximum two:

- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

Create none. Delete none. Do not edit Task Cards during implementation.

## Requirements

1. Validate the persisted predecessor envelope against the persisted old
   attempt identity and unchanged authority bindings before rebinding.
2. After fresh retry identity exists, rebuild the canonical envelope through
   the existing `build_canonical_dispatch_envelope(...)` seam.
3. Both REPAIRABLE and non-REPAIRABLE workforce-bound retries submit an
   envelope whose `attempt_id` equals the fresh attempt.
4. Preserve Planner output/hashes, Workforce Admission demand/binding/policy
   identities, Task Card path/hash, worker/provider/model constraints, semantic
   task identity, allowed scope, verifier contract, retry eligibility,
   absorbing-state rules, cleanup gates, history, and budgets.
5. Missing, malformed, tampered, deliberately stale, or cross-task predecessor
   envelope remains fail-closed before workspace/process creation or worker
   invocation.
6. Do not add a second validator, change Planner/Workforce authority, or widen
   non-workforce retry behavior.

## Acceptance oracle

- `FINAL_BLOCK + ALREADY_REMOVED + non-REPAIRABLE + workforce-bound` retry
  reaches resubmission with `REUSED_TASK_ID` and no real provider execution.
- Fresh attempt/action/idempotency identities differ from the predecessor and
  agree with durable retry metadata.
- The persisted canonical envelope exactly equals the canonical projection from
  unchanged Planner/admission/card/demand bindings plus the fresh attempt.
- Deep equality proves semantic and authority bindings are unchanged.
- Restoring the old attempt-bound envelope fails with
  `WORKFORCE_DISPATCH_ENVELOPE_MISMATCH` before launch.
- Existing REPAIRABLE, invalid-binding, retry-state, absorbing-state, cleanup,
  and history-preservation tests remain green.

## Verification commands

```bash
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k retry
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
git diff --name-status
```

Before commit, inspect tracked/staged deletions, diff stats, and full staged
diff. The changed set must be exactly within the two allowed paths.

## Commit and block policy

The worker may commit only scoped source/test changes. It may not push, merge,
approve, integrate, clean unrelated state, mutate `main`, or select successor
work.

- `HARD_BLOCK`: scope/base/authority drift, predecessor-envelope ambiguity,
  integrity weakening, required scope widening, deletion, or verifier failure.
- `RECOVERABLE_BLOCK`: transient infrastructure failure with reconciled
  unchanged source/session state.
- `REVISE`: bounded correction within the exact two-path contract.

Maximum claim:
`LIFECYCLE_RETRY_DISPATCH_ENVELOPE_REBIND_CLOSED_AT_SOURCE_TEST_CANDIDATE`.

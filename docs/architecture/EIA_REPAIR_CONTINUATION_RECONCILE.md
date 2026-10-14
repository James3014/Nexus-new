# EIA repair continuation reconcile (phase 0, gap 2)

Status: design note. Fanout primitive landed; closure/automation wiring is open.
Date: 2026-10-14.

## Problem

A same-session repair continuation (`AdaptiveWorkerFanoutRuntime.continue_repair`,
bound or unbound) that ends without a proven outcome leaves its attempt
`attempts/<task>--<unit>--repair-dNNN.json` in `OUTCOME_UNKNOWN` (or `DISPATCHING`
after a crash). Before this change nothing could resolve it:

- fanout had a reconcile path only for the initial dispatch (`run` ->
  `_reconcile_initial`);
- `prepare_repair` refused the same repair id (`FANOUT_RECONCILIATION_REQUIRED`)
  but accepted a different repair id for the same unit, so a later continuation
  could race the unknown one on the same session and workspace when the
  workspace happened to be clean;
- closure (`close_task`) propagates the `FanoutError`, automation records
  `RECONCILIATION_REQUIRED` with `prior_state=CLOSURE_DISPATCHING`, and every
  later run returns that record unchanged. The item is parked forever. This is
  safe (fail closed) but the unit can never make progress without manual action.

## What landed (fanout)

- `FanoutStore.existing_repair_attempt(task, unit, repair_id)` and
  `FanoutStore.unresolved_repair_ids(task, unit)`.
- `prepare_repair` refuses any new continuation while another repair attempt of
  the same unit is `PREPARED`/`DISPATCHING`/`OUTCOME_UNKNOWN`.
- `AdaptiveWorkerFanoutRuntime.reconcile_repair(parent_receipt, repair_id=...)`:
  reconcile-only, same semantics as the initial reconcile:
  - never calls `continue_session`; it asks `transport.reconcile_workspace` about
    the attempt's recorded operation id only (plus the recorded Core hashes for a
    bound continuation);
  - the attempt must be `DISPATCHING`/`OUTCOME_UNKNOWN` and must match the parent
    receipt (parent receipt id, session, workspace, expected head);
  - a transport without operation ids is refused (`OPERATION_ID_REQUIRED`): the
    OpenCode directory reconcile returns the latest assistant message of the
    session, which cannot distinguish the repair turn from the parent's turn;
  - the result goes through the same checks as a live continuation
    (`_finalize_repair`: session, operation id, BOUND attestation, model
    attestation, worker result, candidate capture). Any unproven outcome leaves
    the attempt `OUTCOME_UNKNOWN` and raises `FANOUT_RECONCILIATION_REQUIRED`.

### Review hardening (PR #2187)

- Bound-ness of a reconcile comes from the parent receipt
  (`_receipt_core_binding`), backed by the unit's initial attempt record: if the
  parent is BOUND the repair attempt must carry exactly the parent's Core fields
  (else `REPAIR_RECONCILE_CORE_BINDING_MISMATCH`), and the reconcile sends and
  checks the parent's hashes. A parent stripped of its binding while the initial
  attempt is bound fails with `CORE_BINDING_PARENT_RECEIPT_INVALID`.
- The sibling check and the attempt write in `prepare_repair` run under a per-unit
  `fcntl.flock` (`<state>/locks/<task>--<unit>--repair.lock`).
- `unresolved_repair_ids` fails closed: an unreadable record, a wrong
  schema/mode/identity, or a missing/unknown state is unresolved. Only
  `COMPLETED`, `TERMINAL_BLOCKED` and `FAILED` count as resolved.
- `_finalize_repair` checks the attested `directory` against the recorded
  workspace, like the initial finalizer.
- A stale `PREPARED` repair attempt is abandoned, not blocking. Send ordering in
  `continue_repair`: build the prompt, derive the operation id (pure hash, no
  effect), then `prepare_repair` writes `PREPARED` (with the operation id) under
  the lock, then `mark_repair_dispatching` re-reads the record under the lock and
  moves it to `DISPATCHING` only if it is unchanged and still `PREPARED`, and
  only then is `transport.continue_session` called. So `PREPARED` proves the
  transport was never called. A later `prepare_repair` marks such a sibling
  `FAILED` / `ABANDONED_BEFORE_DISPATCH` under the lock, and the abandoned process
  can no longer dispatch (`FANOUT_REPAIR_ATTEMPT_SUPERSEDED`).

### Known limitation: crash after the candidate commit

`_capture_candidate` commits the candidate before the repair receipt and the
`COMPLETED` attempt state are written. If the process dies in between, the
attempt stays `DISPATCHING` while the workspace HEAD is already the new commit.
`reconcile_repair` then gets a COMPLETED result from the transport, but capture
refuses because HEAD is not the parent candidate (`WORKER_COMMIT_FORBIDDEN`).
The unit stays blocked; no continuation is re-sent and no second continuation
can start. This is stuck but safe, and recovery is manual (an operator inspects
the commit). Making it recoverable would need the intended candidate to be
persisted before committing; this is not done here.
Pinned by `test_repair_reconcile_after_post_commit_crash_is_stuck_but_safe`.

## Open: closure and automation wiring (not implemented)

Closure restarts from the initial unit receipts and the durable repair-delta
count. To resume it would need to:

1. For each unit, rebuild the receipt chain from the fanout store (repair
   receipts whose `parent_receipt_id` is the current receipt), so `current`
   points at the newest proven candidate instead of the initial one.
2. If the newest receipt has an unresolved child repair attempt (the delta for
   that repair index is already written), call `c_runtime.reconcile_repair`
   instead of writing a new delta; count it against the same budget slot.
3. Automation must stop treating `RECONCILIATION_REQUIRED` with
   `prior_state=CLOSURE_DISPATCHING` as a permanent park, and resume closure in a
   reconcile-only mode (no new semantic or fanout dispatch).
4. The Core binding freshness still bounds everything: a reconciled continuation
   produces no new effect, so it does not need revalidation, but any *further*
   repair after the reconcile must revalidate as today.

Any future wiring must run closure's `validate_worker_receipt` on the parent
receipt (and `_validate_repair_result` on the reconciled child) before trusting
`reconcile_repair`. Fanout trusts the parent receipt's Core fields as the
binding authority.

Binding window: `binding_validity_seconds` now counts the contract verifiers and
closure's built-in integrity checks, but not closure's 16 other `_run_git` call
sites (30 s timeout each: workspace HEAD, status and tree probes, diff hashing,
composition). Only the fixed 120 s margin covers them, so a worst-case cycle can
still outlive the window.

Step 3 changes an explicit fail-closed rule of the automation state machine, so it
needs an owner decision. The strict xfail test
`tests/services/test_external_intelligence_closure.py::test_closure_resume_reconciles_unknown_repair_continuation_without_redispatch`
pins the intended behaviour.

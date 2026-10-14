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

## Threat model and known stuck-but-safe states

The repair guards are designed for crash safety and to prevent a double
dispatch: a continuation is never sent twice, and two continuations never run
on one session. The fanout store is local state that only the daemon writes.
Resisting tampering with it is best-effort and out of scope. For example,
rewriting `prepare_seq` or the per-unit counter
(`<state>/locks/<task>--<unit>--repair.seq`) can mis-order supersession; in
review, no duplicate send was reproduced this way. Initial-attempt Core
evidence is value-checked (well-formed hashes), not authenticated.

Known stuck-but-safe states that need operator action:

- **Crash between the sent-marker and the DISPATCHING write.** The attempt is
  still `PREPARED`, but `<state>/repair-sent/<attempt_id>` exists. It is never
  abandoned or reconciled, so the unit stays blocked.
- **Pre-change `PREPARED` repair records without `prepare_seq`.** They can be
  abandoned, but an abandoned record without `prepare_seq` is never proven
  resolved, so the unit stays blocked.
- **Crash after the candidate commit** (see the earlier section on this crash).

The sent-marker is created with `O_EXCL` but is not fsynced, and neither is its
directory. Whether it survives a power loss is not guaranteed; a process crash
alone does not lose it.

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
needs an owner decision. The intended behaviour is pinned by the acceptance test
below (`test_closure_resume_reconciles_unknown_repair_continuation_without_redispatch`).

## Acceptance test for the deferred closure wiring

The PR impact gate rejects newly added test ids that do not pass (a strict
`xfail` counts as not passing), so the expected closure behaviour is kept here
instead of in `tests/services/test_external_intelligence_closure.py`. Add it to
that file, without the `xfail`, together with the closure/automation wiring:

```python
class _UnknownThenReconcilableCRuntime(RepairingCRuntime):
    """First continuation ends OUTCOME_UNKNOWN; only reconcile_repair may resolve it."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reconciled: list[str] = []
        self._pending: tuple[dict, str, str, str] | None = None

    def continue_repair(self, receipt, *, repair_id, repair_ref, repair_sha256):
        if self._pending is None:
            self._pending = (dict(receipt), repair_id, repair_ref, repair_sha256)
            from nexus.services.external_intelligence_fanout import FanoutError

            raise FanoutError("FANOUT_RECONCILIATION_REQUIRED")
        raise AssertionError("blind redispatch of a repair with unknown outcome")

    def reconcile_repair(self, receipt, *, repair_id):
        assert self._pending is not None
        parent, pending_id, ref, sha = self._pending
        assert repair_id == pending_id and receipt["receipt_id"] == parent["receipt_id"]
        self.reconciled.append(repair_id)
        return super().continue_repair(
            receipt, repair_id=repair_id, repair_ref=ref, repair_sha256=sha
        )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "EIA phase 0 gap 2: closure/automation have no resume path for a repair "
        "continuation that ended OUTCOME_UNKNOWN (fanout reconcile_repair exists; "
        "closure wiring is a design decision, see "
        "docs/architecture/EIA_REPAIR_CONTINUATION_RECONCILE.md)"
    ),
)
def test_closure_resume_reconciles_unknown_repair_continuation_without_redispatch(tmp_path):
    repo, _base = make_repo(tmp_path)
    card_ref, card_hash, head_sha = make_task_card(repo)
    receipt = make_receipt(repo, tmp_path, head_sha, "ua", "a.py", "A = 1\n")
    c_runtime = _UnknownThenReconcilableCRuntime(repo, head_sha, {"ua": ("a.py", "A = 2\n")})
    kwargs = dict(
        main_sha=head_sha,
        unit_receipts=[receipt],
        unit_verifiers={
            "ua": [
                verifier(
                    "a-two", "from pathlib import Path; assert 'A = 2' in Path('a.py').read_text()"
                )
            ]
        },
        whole_verifiers=[verifier("whole", "raise SystemExit(0)")],
        task_card_ref=card_ref,
        task_card_hash=card_hash,
    )
    with pytest.raises(Exception, match="FANOUT_RECONCILIATION_REQUIRED"):
        runtime(repo, tmp_path, c_runtime=c_runtime, max_repairs=1).close_task(**kwargs)
    resumed = runtime(repo, tmp_path, c_runtime=c_runtime, max_repairs=1).close_task(**kwargs)
    assert c_runtime.reconciled == ["d001"]
    assert resumed["status"] == CLAIM_CEILING
```

# Issue 1274 — Agy Child Ownership, Crash Consistency, and Surviving Provider Reconciliation

- task_id: `github-issue-1274-child-ownership-crash-consistency`
- campaign_id: `github-issue-1274-child-ownership-crash-consistency`
- status: `CANDIDATE`
- owner: `James Chen (James3014)`
- coordinator: `Antigravity Engineer`
- issue: `https://github.com/James3014/Nexus-new/issues/1274`
- durable_marker: `AGY_CHILD_OWNERSHIP_CRASH_CONSISTENCY_ENFORCED`
- AUTO_CHAIN: `false`

## Objective

Prevent divergence between durable operation state and surviving physical provider child processes when a dispatcher wrapper dies or crashes. Establish:

1. Non-Terminality while Provider Child Survives (`DirectOperationJournal.reconcile`):
   - When a wrapper process dies (`pid_alive == False`), if the provider child is still running (`provider_alive == True`), the operation must NOT transition to a terminal state (`OUTCOME_UNKNOWN` or `FAILED`).
   - The operation transitions to `status="RUNNING"`, `phase="RECONCILE_REQUIRED"` with `reconciliation.result="PROVIDER_PROCESS_STILL_RUNNING"` and `retry_permitted=False`.

2. Physical Provider Discovery on Unrecorded/Orphaned Children (`AgyOperationJournal.reconcile`):
   - When the wrapper PID is dead, if `provider_pid` was not recorded in the durable journal (or has unverified state), scan for active processes matching the operation marker (`--log-file <operation_dir>/agy.log` or `<operation_id>/agy.log`).
   - If an active provider process is discovered, bind its physical identity (`provider_pid`, `provider_pgid`, `provider_process_state="RUNNING"`) before proceeding with process group cleanup.

3. Bounded Child Termination and Clean Terminalization:
   - When an orphaned provider child/process group is discovered, execute bounded TERM -> KILL escalation.
   - If surviving processes remain (`alive_after == True` or `unverified == True`), keep the operation non-terminal in `phase="RECONCILE_REQUIRED"` with `retry_permitted=False`.
   - Only when physical child truth is bounded (`provider_alive_after == False`), mark terminal `OUTCOME_UNKNOWN` with `reconciliation.result="ORPHAN_PROVIDER_TERMINATED"`.

4. Workflow Doctor Crash-Aware Liveness Detection:
   - In `workflow_doctor`, active operations whose wrapper PID is no longer alive are classified as requiring reconciliation (`reconcile_active`), returning `RECONCILE` with `code="RECONCILE_OPERATION"` rather than stalling in `WAIT: OBSERVE_ACTIVE_OPERATION`.

## Allowed Files

- `nexus/services/direct_operation_journal.py`
- `nexus/services/agy_operation_journal.py`
- `nexus/services/workflow_doctor.py`
- `tests/services/test_agy_operation_journal.py`
- `tests/services/test_workflow_doctor.py`
- `tasks/github-issue-1274-child-ownership-crash-consistency/00-child-ownership-crash-consistency.md`
- `tasks/github-issue-1274-child-ownership-crash-consistency/INDEX.md`

## Acceptance Criteria

1. Deterministic regression verifies that `DirectOperationJournal.reconcile` does not mark an operation terminal when `pid` is dead but `provider_pid` is running.
2. Deterministic regression verifies that `AgyOperationJournal.reconcile` discovers an unrecorded surviving provider child via operation marker, binds its identity, and stops it without premature terminalization.
3. If an orphaned child cannot be stopped, the operation remains in `phase="RECONCILE_REQUIRED"`, `provider_alive_after=True`, `retry_permitted=False`.
4. `workflow_doctor` detects active operations with dead wrapper PIDs and triggers `RECONCILE_OPERATION`.
5. All focused unit tests pass, Ruff check passes, Ruff format check passes, and git diff check passes.

## Claim Ceiling

Source candidate and verified test suite only. No unilateral acceptance, merge, runtime activation, or release authority.

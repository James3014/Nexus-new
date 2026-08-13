---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-7-m3-d-events-e2e
campaign_id: github-issue-7-acceptance-repair-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/7
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
---

# M3-D Ordered Attempt Events and End-to-End Acceptance

## Objective

Reuse the existing append-only event log to emit ordered auditable task/attempt
transitions for create, verify, accept, repair, and block, then prove the full
M3 structural loop and manual-path compatibility. Persisted attempt records must
remain fail-closed across restart and hostile writes: contiguous per-attempt
sequence, parent/record digest chain, cross-process locking, tamper detection,
and legacy attempt-record rejection are required. The implementation must keep
the claim boundary explicit: state write succeeds before event append is
claimed, and an append failure cannot be reported as a completed state write.

## Dependency

M3-C completed and exact-reviewed.

## Allowed files

- `nexus/events/contracts.py`
- `nexus/events/log_store.py`
- `nexus/events/transport.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/acceptance_loop.py`
- `tests/core/test_event_bus.py`
- `tests/events/test_lifecycle_phase_receipts.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_acceptance_loop.py`

Maximum implementation/test files changed: 9. Governance card/INDEX amendments
do not count toward this implementation ceiling.

## Required behavior

- every emitted transition has first-class `task_id`, `attempt_id`, ordered
  sequence, state/reason, Candidate/evidence refs, and timestamp
- events are append-only and replay-order deterministic
- persisted attempt tails are reconstructed after restart, with per-attempt
  sequence and parent/record digest continuity verified before append/read
- concurrent writers use cross-process locking; tampered, truncated, malformed,
  non-contiguous, or legacy attempt records fail closed
- state-write-before-event-append ordering is explicit in the service contract;
  no event receipt may claim a state mutation that did not persist
- no raw hidden chain-of-thought payload
- no compaction, resume loader, cross-agent rehydration, or #31 policy
- E2E proves ACCEPT, REPAIRABLE to new attempt, BLOCK, exhaustion,
  provider-failure distinction, and unchanged manual lifecycle

## Verification and exit

Focused event ordering/tamper/restart/locking/legacy-record hostile tests and M3
E2E suites, affected lifecycle regressions, Ruff, Pyright, `git diff --check`;
exact commit and independent review. Final claim ceiling is
`M3_ACCEPTANCE_REPAIR_IMPLEMENTED`, never runtime activated or public-production
ready.

## Block classification

`RECOVERABLE_BLOCK` for bounded defects; `HARD_BLOCK` for event tamper,
continuity-scope expansion, hidden-CoT persistence, state/event claim inversion,
legacy-record acceptance, or authority collapse. #31, #65, #191, and #143 are
explicitly excluded from this card.

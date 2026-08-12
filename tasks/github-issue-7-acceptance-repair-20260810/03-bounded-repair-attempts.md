---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: github-issue-7-m3-c-bounded-repair
campaign_id: github-issue-7-acceptance-repair-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/7
owner_gate: M3_C_CAMPAIGN_REBIND_AND_OWNER_GATE
owner_gate_status: GRANTED_2026_08_12
baseline_main: 89ed130ac5d3ad58106e7d9ba8f0d3a65066fdc2
current_main: 9125913ca809c954806386e3f11e6eb799ff882f
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
---

# M3-C Bounded Repair Attempts and Physical Ceilings

The Owner granted `M3_C_CAMPAIGN_REBIND_AND_OWNER_GATE` on 2026-08-12 for
bounded implementation, commit, issue-branch push, and pull-request creation.
M3-B is physically complete. This grant does not authorize approval,
integration, merge, successor work, release, or production/public claims.

## Objective

For REPAIRABLE only, create a new immutable attempt/Candidate lineage and have
CapabilityPlanner plus Workforce Admission select the repair worker. Enforce
aggregate attempts, provider calls, absolute task deadline, and actual changed
file cardinality without resetting budgets on retry/fallback.

## Dependency

M3-B completed and exact-reviewed.

## Allowed files

- `nexus/orchestrator/task_contract.py`
- `nexus/orchestrator/candidate_verifier.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/acceptance_loop.py`
- `tests/nexus/orchestrator/test_candidate_verifier.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_acceptance_loop.py`

Maximum changed files: 7.

## Required behavior

- repair never mutates an accepted/verified Candidate in place
- each repair has a new attempt id and Candidate state
- attempts/provider calls are aggregate across retries and fallbacks
- wall-time uses one absolute task deadline
- actual changed + untracked + deleted file cardinality is bounded
- exhaustion returns deterministic BLOCK with no additional provider call

## Verification and exit

Focused retry, exhaustion, clock, provider failure, file-count, lineage, and
tamper tests; Ruff, Pyright, `git diff --check`; exact commit and independent
review.

## Completion evidence

PR #188 Candidate head `0bfb31ebc4dc5862581fe6cf289dea43c8942302`
was physically merged as `892369a93a5c540042f0b4b35d1ee8d81a9de2b2`.
The exact seven-file scope received independent `ACCEPT`; required checks were
terminal PASS. Focused evidence included 297 combined tests, eight M3-C tests,
and 311 primary tests. This completion does not activate M3-D.

## Block classification

`RECOVERABLE_BLOCK` for bounded defects; `HARD_BLOCK` for budget reset, in-place
Candidate rewrite, or router/approval authority expansion.

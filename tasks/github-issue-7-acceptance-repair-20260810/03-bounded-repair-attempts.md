---
artifact_authority: current
owner: James Chen
status: PENDING
task_id: github-issue-7-m3-c-bounded-repair
campaign_id: github-issue-7-acceptance-repair-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/7
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# M3-C Bounded Repair Attempts and Physical Ceilings

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

## Block classification

`RECOVERABLE_BLOCK` for bounded defects; `HARD_BLOCK` for budget reset, in-place
Candidate rewrite, or router/approval authority expansion.

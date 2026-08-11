---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: github-issue-22-actionable-semantics
campaign_id: github-issue-22-actionable-semantics-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/22
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: Separate Required Action from Historical Retry

## Objective

Make the public actionable projections represent unresolved current action,
while preserving optional retry hints and durable evidence for settled terminal
records.

## Inputs and dependencies

- Issue #5 / PR #19 is physically merged.
- Issue #6 / PR #36 is physically merged as
  `15c2f7c78c7e7a54327ab4aeaf8c2fdaa0751592`.
- Fresh GitHub overlap audit after that merge found no open pull requests.
- Read-only post-#6 localization found the change bounded to the four runtime
  and focused-test files below.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tasks/github-issue-22-actionable-semantics-20260810/INDEX.md`
- `tasks/github-issue-22-actionable-semantics-20260810/00-required-action-classification.md`

Maximum changed files: 6.

## Forbidden scope

- lifecycle JSON/schema migration or historical-state deletion
- bulk retry, cancel, reconcile, cleanup, approval, Candidate, or integration
  mutation
- new lifecycle framework, registry, policy engine, Router, or state machine
- Planner, Workforce policy, provider, route, release, or public-claim changes
- runtime activation or live lifecycle mutation

## Required behavior

- A cleaned candidate-less `FINAL_BLOCK` with `promotion_status=NOT_CREATED`,
  no unresolved reconciliation or cleanup state, and cleanup conclusively
  `REMOVED`, `ALREADY_REMOVED`, or `TARGET_CLEANED` is non-actionable.
- Preserve its terminal status, durable evidence, and optional
  `retry_same_task` hint without using retry availability as current-action
  truth.
- Candidate, approval, integration, retained-target, uncertain-mutation,
  cleanup-failure, and reconciliation-required states remain actionable.
- Settled Assisted `FAILED` and `CANCELLED` records with reconciliation false
  and cleanup conclusively settled are non-actionable while preserving evidence
  and optional `nexus_task_retry` guidance.
- `UNKNOWN_REQUIRES_RECONCILE` remains actionable with
  `nexus_task_reconcile`.
- `_assist_response()` or one minimal pure helper is the canonical Assisted
  classification consumed by response, public actionable listing, and gateway
  counts; remove independent status-membership truth.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-issue22-pycache uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/services/test_runtime_workforce_admission.py`
- Run Ruff check on the four allowed runtime/test files at exact base and
  Candidate; require zero new diagnostics. The frozen base has eight findings.
- Run Ruff format check on the same four files at exact base and Candidate;
  require zero newly unformatted files. All four are already unformatted at
  exact base, so broad formatting cleanup is out of scope.
- `git diff --check`
- allowed-file, deletion, complete staged-diff, and card-hash audit

## Required evidence and exit criteria

- State-based tests cover all three accepted cleanup statuses.
- Negative tests preserve actionability for unresolved Candidate, approval,
  integration, cleanup, uncertain mutation, and reconciliation state.
- Settled and unresolved Assisted `FAILED`/`CANCELLED` plus
  `UNKNOWN_REQUIRES_RECONCILE` are covered.
- Public list and gateway count consume the same classification and do not
  duplicate Assisted tasks.
- Retry/evidence preservation is asserted separately from current action.
- Focused tests, exact-base Ruff differential gates, diff gate, and independent
  review pass.

Maximum claim: covered self-hosted and Assisted projections distinguish
unresolved required action from settled historical retryable records. This does
not delete history, reconcile tasks, or change lifecycle authority.

## Completion receipt

- Reconciled authority card SHA-256 before implementation commit:
  `1ffb6ec9218145735e95c45c9190cbc1e39ce989b3d98286fff0b777ba7b3a81`.
- Implementation commit: `aeeb19db1`.
- Exact card suite: 321 passed with 6 pre-existing warnings.
- Adversarial review: 31 self-hosted hidden-state combinations and 10 Assisted
  settlement/reconciliation/uncertainty combinations passed; ACCEPT with no
  P0/P1.
- Exact-base Ruff differential: zero new findings; base and Candidate each
  report the same eight findings.
- Exact-base format differential: zero new failures; the same four files are
  unformatted at base and Candidate.
- `git diff --check`: passed.
- Scope: exactly four implementation/test files plus campaign receipts; no
  deletions or lifecycle/runtime mutation.

## Block classification

- `RECOVERABLE_BLOCK`: bounded implementation or regression defect.
- `HARD_BLOCK`: acceptance requires lifecycle/schema/authority mutation or
  files outside the frozen scope.

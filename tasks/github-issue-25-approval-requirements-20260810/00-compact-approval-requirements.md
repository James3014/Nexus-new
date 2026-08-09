---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: github-issue-25-approval-requirements
campaign_id: github-issue-25-approval-requirements-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/25
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: Expose Compact Architecture Approval Requirements

## Objective

Expose a bounded, read-only `approval_requirements` projection in the existing
compact task snapshot so an Owner can construct the current
`nexus.architecture_approval.v1` acknowledgement without guessing or reading an
oversized state object.

## Inputs and dependencies

- Architecture Approval seams are present in both collaboration and local
  runtime histories; no framework transplant is required.
- Issue #6 / PR #36 physically merged.
- Issue #22 / PR #38 physically merged as
  `08e2c921b5082ac0a54d407fb51de3a7f33d6284`.
- Fresh post-merge open-PR overlap audit returned no open pull requests.
- `nexus_task_status` already delegates to `get_task_snapshot()`, so no Gateway
  source change is currently required.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tasks/github-issue-25-approval-requirements-20260810/INDEX.md`
- `tasks/github-issue-25-approval-requirements-20260810/00-compact-approval-requirements.md`

Maximum changed files: 4.

## Forbidden scope

- approval creation, validation-rule, expiry, consumption, integration, or
  Candidate mutation
- lifecycle schema migration or historical state rewrite
- Gateway/public mutation tools
- Router, Planner, Workforce, provider, release, or runtime activation changes
- guessed or caller-supplied binding promoted to durable truth

## Required behavior

- Derive only from current durable task, promotion packet, Candidate, and
  verified-receipt state.
- For authority-change-required state, project schema, required flag, bound
  task/attempt, Candidate commit/tree, `authority_findings_sha256`, typed
  completeness/approvability, missing fields, and mismatches.
- `APPROVABLE` means only that durable binding inputs are complete and mutually
  consistent; it does not mean approved, valid for use, unexpired, or consumed.
- Missing or malformed task/attempt/commit/tree/findings hashes and disagreement
  between durable sources produce `INCOMPLETE` / `NOT_APPROVABLE` with explicit
  deterministic reasons.
- Non-authority-change tasks omit the projection or return one deterministic
  non-required form; stale approval-shaped data cannot request approval.
- Existing one-shot approval validator remains the sole mutation-time authority.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-issue25-pycache /Users/jameschen/Workspace/nexus/.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py`
- Compare Ruff check and format results for the two implementation/test files
  against exact base; require zero new diagnostics or newly unformatted files.
- `git diff --check`
- allowed-file, deletion, complete staged-diff, and card-hash audit

## Exit criteria

- Complete positive binding and missing task/attempt/commit/tree/findings cases.
- Packet/verified-receipt mismatch and stale/non-required cases fail closed.
- Compact snapshot contains no secret, approval grant, or new mutation surface.
- Exact tests, differential style gates, diff gate, and independent review pass.

Maximum claim: the existing fail-closed Architecture Approval contract is
operator-executable from one compact read-only status projection without
widening approval authority.

## Block classification

- `RECOVERABLE_BLOCK`: bounded projection or test defect.
- `HARD_BLOCK`: acceptance requires approval semantics/schema mutation or files
  outside the frozen scope.

## Completion receipt

- Implementation commit: `e1a834a00f2d327a67ef4125a053a2e9c5eeb3fa`
- Exact-commit independent review: ACCEPT; no P0/P1 findings
- Service suite: 235 passed
- Malicious approval probes: 24 passed
- Focused Gateway tests: 2 passed
- Compact/detailed parity, no-mutation, strict type/hash, malformed/empty source,
  diff, scope, and deletion gates passed
- Ruff differential: no new findings beyond exact-base debt

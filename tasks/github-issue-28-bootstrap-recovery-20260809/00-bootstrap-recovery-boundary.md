---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-28-bootstrap-recovery-boundary
campaign_id: github-issue-28-bootstrap-recovery-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/28
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: External Bootstrap Recovery Boundary

## Objective

Persist one fail-closed recovery rule for the narrow case where Nexus cannot
truthfully use its defective self-hosting authority to repair that authority.

## Dependencies

- Issue #28 is Ready.
- Exact base: `d934a7c49d40ea7ec908f754845965fa11103ae6`.
- Documentation/governance only; no runtime mutation.

## Allowed files

- `AGENTS.md`
- `docs/governance/rollback_runbook.md`
- `tests/ops/test_bootstrap_authority_files.py`
- `tasks/github-issue-28-bootstrap-recovery-20260809/INDEX.md`
- `tasks/github-issue-28-bootstrap-recovery-20260809/00-bootstrap-recovery-boundary.md`

Maximum changed files: 5.

## Forbidden scope

- Runtime, lifecycle, Gateway, route, workforce, schema, or provider code
- A second Router, Planner, lifecycle, approval, integration, or release path
- Candidate approval, integration, push, reload, activation, or cleanup
- Weakening normal governed execution for healthy failures

## Verification

- `/Users/jameschen/Workspace/nexus/.venv/bin/python -m pytest -q tests/ops/test_bootstrap_authority_files.py tests/ops/test_bootstrap_context_budget.py`
- `git diff --check`
- Changed-file and deletion audit

## Required evidence

- Exact base and card SHA-256
- Complete scoped diff
- Focused test output
- Independent primary-agent review

## Exit criteria

- Trigger requires a real self-hosting authority identity defect.
- Ordinary failures remain on the normal governed path.
- Recovery uses an exact clean base, bounded isolated repair, frozen identity,
  independent verification, and separately authorized activation.
- Normal canonical governance resumes after identity is re-established.

## Block classification

- `RECOVERABLE_BLOCK`: focused wording/test failure within allowed scope.
- `HARD_BLOCK`: source requires runtime behavior or a second authority.

## Completion evidence

- Exact base: `d934a7c49d40ea7ec908f754845965fa11103ae6`.
- Root authority remains within the 12,000-byte context budget.
- Focused bootstrap, context-budget, and protocol tests pass.
- The diff changes documentation/governance instructions only; no runtime
  authority or behavior is added.

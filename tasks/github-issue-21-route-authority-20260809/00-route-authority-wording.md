---
artifact_authority: current
owner: James Chen
status: IMPLEMENTED_PENDING_PR
task_id: github-issue-21-route-authority-wording
campaign_id: github-issue-21-route-authority-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/21
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: Route Authority Wording

## Objective

Make the three agent-facing governance surfaces state the existing source
contract precisely: `CapabilityPlanner` is the sole route/capability-selection
authority; `HybridRouteDecision` is the Planner-derived decision
contract/projection and is not a second selector, router, or planner.

## Dependencies

- GitHub Issue #21 is Ready.
- Base revision: `d2e25f19dc93d2ea87a2117919a8e140ac323719`.
- No runtime implementation change is authorized.

## Allowed files

- `AGENTS.md`
- `docs/agents/WORKFORCE_EXECUTION_OVERLAY.md`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `tasks/github-issue-21-route-authority-20260809/INDEX.md`
- `tasks/github-issue-21-route-authority-20260809/00-route-authority-wording.md`

Maximum changed files: 5.

## Forbidden scope

- Runtime source or tests
- Route, planner, topology, lifecycle, schema, model, or workforce-policy behavior
- Candidate approval, integration, push, or runtime activation

## Verification

- Focused route-freeze and authority tests selected from current source
- `git diff --check`
- Changed-file and deletion audit

## Required evidence

- Exact base and card hash
- Complete scoped diff
- Focused test output
- Independent primary-agent review

## Exit criteria

- All three governance surfaces express the same sole-selector distinction.
- No runtime or unrelated governance change is present.
- Required verification passes.

## Block classification

- `RECOVERABLE_BLOCK`: test or formatting failure within allowed scope.
- `HARD_BLOCK`: source contradicts Issue #21 or another authority requires
  runtime/policy changes.

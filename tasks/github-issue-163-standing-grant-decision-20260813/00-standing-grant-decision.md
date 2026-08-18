# Issue #163 Phase B — Evidence-only standing-grant decision (Historical)

artifact_authority: historical
status: superseded
superseded_by: tasks/standing-owner-autonomy-20260811/02-standing-grant-normal-phase-authority.md

## Objective

Bind owner/coordinator/repository/thread/goal/actions/time/revocation and a
canonical context hash, then evaluate a request as `GRANT_MATCH`,
`OUT_OF_SCOPE`, `INVALID`, `OWNER_MERGE_SLOT_REQUIRED`, or
`PLATFORM_APPROVAL_REQUIRED`. `GITHUB_MERGE` always returns
`OWNER_MERGE_SLOT_REQUIRED`.

## Allowed files

- `nexus/contracts/autonomy_goal.py`
- `nexus/orchestrator/autonomy_policy.py`
- `tests/nexus/orchestrator/test_autonomy_goal_policy.py`
- this campaign's Task Card and `INDEX.md`

## Forbidden

No Gateway, service, merge, lifecycle, #8, route, or existing shadow evaluator
rewiring. The decision is immutable evidence and always has
`mutation_authorized=False`.

## Verification and exit

Run the focused policy test, ruff on the three implementation/test files, and
`git diff --check`. Stop at a scoped commit; no push or approval is performed by
the worker.

## Block class

`HARD_BLOCK` if the contract would require a second authority or platform
mutation capability.

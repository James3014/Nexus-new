# Issue #163 Phase B — Evidence-only standing-grant decision

Status: ACTIVE — `CANDIDATE_PENDING_OWNER_RECONCILIATION`
Terminal disposition: KEEP_OPEN (Issue #163 remains OPEN; no merge without
fresh independent acceptance and an Owner terminal disposition)
Reconciled/current main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
Historical baseline: `f3dc8d28a0f90d5c5fd2f31dbeb0ab2f29f7ca04`
Historical reconciled main: `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`
Marker/ceiling (candidate evidence):
`CANONICAL_GITHUB_MERGE_SLOT_AND_STANDING_GRANT_EVIDENCE_VERIFIED`

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

## Candidate evidence

`GITHUB_MERGE` always returns `OWNER_MERGE_SLOT_REQUIRED`; the decision is
immutable evidence and always has `mutation_authorized=False`. PR234 is
consumer evidence only; protected merge remains `OWNER_MERGE_SLOT_REQUIRED`.
Exact history binds PR222 head `ff483f263cc603aea98ae7c38ca4c0ec56d1b1d7` to
merge `e900ed6df092aac2d2333cc1db74f499a5881e7f`; PR223 head
`6536a749203fcae11d18f8894650fa0d82e495b5` to merge
`f2f808166e735e271c793c6e939af8071d985cff`; and PR234 consumer head
`87998b0e1c555170b91062e902d6a9c5aae36a21` to merge
`8e0986b40db56016c79b03eb81ff3d03c85c6f32`. These are historical acceptance
references only; no current CI or approval is asserted. Issue #163 remains
OPEN with `KEEP_OPEN`; no merge without fresh independent acceptance and an
Owner terminal disposition.

## Block class

`HARD_BLOCK` if the contract would require a second authority or platform
mutation capability.

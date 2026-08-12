# Task Card: Issue 106 Exact-Head CAS and Post-Apply Verification

## Objective

Add one bounded, fail-closed guard that binds authorized cleanup integration
evidence to an exact PR base/head/tree and trusted required-check receipt,
emits an exact CAS token before integration, and verifies the physical merge and
deleted-path state afterward.

## Authority and dependencies

- Owner request: continue Issue #51 by completing its prerequisite chain first.
- Issue: `#106`
- Exact baseline: `21add665679acaa57a795296dfef2f5b4e49af27`
- Hard prerequisites: `#104` and `#105`, both physically completed.
- `AUTO_CHAIN=false`.

## Allowed files

- `scripts/ops/cleanup_integration_guard.py`
- `tests/ops/test_cleanup_integration_guard.py`
- `tasks/github-issue-106-cleanup-integration-cas-20260812/INDEX.md`
- `tasks/github-issue-106-cleanup-integration-cas-20260812/00-exact-head-cas-post-apply.md`

## Forbidden scope

- PR #71 / Issue #51 product or deletion files
- GitHub ruleset or protected-workflow mutation
- Candidate, approval, merge, integration, route, lifecycle, Workforce, release,
  or production authority
- admin/manual bypass, force push, ref deletion, history rewrite

## Required behavior

1. Validate an exact manifest containing repository, PR, base ref/SHA, head
   SHA/tree, changed/deleted paths, and required check source identities.
2. Immediately fail closed on stale base/head/tree, draft/non-mergeable PR,
   missing/failed/non-terminal check, wrong check source, stale check head, or
   duplicate required-check evidence.
3. Emit a deterministic preflight receipt and CAS token. A dry-run receipt is
   evidence only and cannot authorize post-apply verification.
4. Post-apply verification must reject manifest changes, replayed CAS tokens,
   concurrent target movement, non-exact merge parentage, physical diff drift,
   incomplete deletion inventory, or any deleted path still present.
5. The guard never performs the merge. The existing authorized integration
   action remains responsible for exact-head apply/CAS.

## Verification

- focused hostile tests for exact/stale head, base drift, check source/status,
  manifest drift, replay, concurrent apply, merge parentage, diff inventory, and
  deleted-path absence
- `python3 -m compileall -q scripts/ops/cleanup_integration_guard.py tests/ops/test_cleanup_integration_guard.py`
- `ruff check scripts/ops/cleanup_integration_guard.py tests/ops/test_cleanup_integration_guard.py`
- `git diff --check`
- one bounded exact-head dry-run receipt

## Exit criteria

A four-file Candidate PR on fresh `main` has terminal required checks, an
independent exact-head acceptance, and proves the hostile tests without changing
merge authority. Maximum claim before physical merge:
`CLEANUP_INTEGRATION_CAS_GUARD_CANDIDATE`.

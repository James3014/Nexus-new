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

## Terminal reconciliation (post-merge, governance-only)

Status: `COMPLETE / TERMINAL_RECONCILIATION`.

The four-file Candidate was merged via PR #202 and the guard now exists in
current `main` `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601` (historical
verification receipt `eb668fb76f0c30d8f025db42cdb8e320d556c037` from the
2026-08-13 snapshot):

- PR #202 base: `21add665679acaa57a795296dfef2f5b4e49af27`
- PR #202 head: `7eccc17a4adf807c7b8724be178dcf2cf624d18a`
- PR #202 merge commit: `bdcc427f6249406079c85f9725b3af6cd62ab1f1`
- exact scope: 4 files changed, 0 deletions; merge commit verified as an
  ancestor of current `nexus-new/main`
- exact-head required checks terminal success: Ruff run `31585645803`,
  Bandit run `31585645820`, Pyright run `31585645787`, Wiki Exact-Base
  Governance run `31585645790`, Pytest run `31585645807`, Exact-base impact
  gate success, Trusted verifier (default branch) integration id `15368`
  success
- independent acceptance: Owner comment `5265336411`
  (`ACCEPT_EXACT_CANDIDATE` / `READY_FOR_COORDINATOR_PROTECTED_MERGE`)

Marker: `CLEANUP_INTEGRATION_CAS_GUARD_PROVEN`.
Claim ceiling: `CLEANUP_INTEGRATION_CAS_GUARD_PROVEN_ONLY`.

Historical baseline `21add665679acaa57a795296dfef2f5b4e49af27` and the original
Candidate wording above are preserved. This card records repository-contained
guard source, tests, and governance it asserts metadata only; no authority over,
and takes no claim for, Issue #51 / PR #71 deletion work, ruleset or
protected-workflow mutation, approval, integration, merge, runtime, release, or
production.

`AUTO_CHAIN=false`.

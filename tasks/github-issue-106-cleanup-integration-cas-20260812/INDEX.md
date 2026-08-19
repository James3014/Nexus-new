---
artifact_authority: current
owner: James Chen
status: completed
purpose: Govern Issue #106 exact-head cleanup CAS and post-apply verification.
---

Historical source-PR current-main binding: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`; retained as historical evidence after the Issue #428 active rebind.

# Issue 106 Cleanup Integration CAS

- Issue: `#106`
- Baseline: `21add665679acaa57a795296dfef2f5b4e49af27`
- Prerequisites: `#104` completed, `#105` completed
- AUTO_CHAIN: `false`
- Active card: `00-exact-head-cas-post-apply.md`
- Claim ceiling: `CLEANUP_INTEGRATION_CAS_GUARD_CANDIDATE`

This campaign adds a fail-closed evidence guard only. It does not create another
merge, approval, Candidate, route, lifecycle, release, or production authority.
The later #51 / PR #71 cleanup remains outside this Task Card.

## Terminal reconciliation (post-merge, governance-only)

Status: `COMPLETE / TERMINAL_RECONCILIATION`.

Reconciled current main: `71ae533ec9f795477131645f96cea1c93b4f4d40`
(previous reconciled snapshot
`cdf2570ede5ae218f36f886b696c8da45458043a`; historical verification receipt
`eb668fb76f0c30d8f025db42cdb8e320d556c037` from the 2026-08-13 snapshot).

Physical implementation merged via PR #202:

- base: `21add665679acaa57a795296dfef2f5b4e49af27`
- head: `7eccc17a4adf807c7b8724be178dcf2cf624d18a`
- merge commit: `bdcc427f6249406079c85f9725b3af6cd62ab1f1`
- exact scope: 4 files changed, 0 deletions
  (`scripts/ops/cleanup_integration_guard.py`,
  `tests/ops/test_cleanup_integration_guard.py`, this `INDEX.md`, and
  `00-exact-head-cas-post-apply.md`)
- merge ancestry: verified `bdcc427f6249406079c85f9725b3af6cd62ab1f1` is an
  ancestor of current `nexus-new/main`
- required checks terminal success on exact head:
  Ruff run `31585645803`, Bandit run `31585645820`, Pyright run `31585645787`,
  Wiki Exact-Base Governance run `31585645790`, Pytest run `31585645807`,
  Exact-base impact gate success, Trusted verifier (default branch) integration
  id `15368` success
- independent acceptance: Owner comment `5265336411`
  (`ACCEPT_EXACT_CANDIDATE` / `READY_FOR_COORDINATOR_PROTECTED_MERGE`)

Marker: `CLEANUP_INTEGRATION_CAS_GUARD_PROVEN`.
Claim ceiling: `CLEANUP_INTEGRATION_CAS_GUARD_PROVEN_ONLY`.

This reconciliation records repository-contained guard source, tests, and
governance metadata only. It asserts no authority over, and takes no claim for,
Issue #51 / PR #71 deletion work, ruleset or protected-workflow mutation,
approval, integration, merge, runtime, release, or production.

`AUTO_CHAIN=false`.

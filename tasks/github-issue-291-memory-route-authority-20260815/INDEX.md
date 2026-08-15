---
campaign_id: github-issue-291-memory-route-authority-20260815
issue: 291
repository: James3014/Nexus-new
status: COMPLETE
terminal_state: TERMINAL_RECONCILIATION
baseline_main: cdf2570ede5ae218f36f886b696c8da45458043a
reconciled_main: b537a7120f79f73029513c4ed83ef325be4a7466
current_frontier: github-issue-291-memory-route-authority-isolation-20260815.md
readiness_marker: LEGACY_MEMORY_ROUTE_AUTHORITY_ISOLATED
claim_ceiling: LEGACY_MEMORY_ROUTE_AUTHORITY_ISOLATED_PROVEN_ONLY
AUTO_CHAIN: false
authorized_deletions: []
---

# Issue #291 — isolate legacy memory route authority

Issue #291 is Ready for a bounded Candidate after exact-main source
localization and fresh Workforce Admission. The only implementation slice is
the legacy `CapabilitySelector` dynamic-learning-policy add/remove step and its
focused hostile tests.

- Current frontier: `github-issue-291-memory-route-authority-isolation-20260815.md`.
- Historical candidate baseline: `cdf2570ede5ae218f36f886b696c8da45458043a`.
- Physical implementation merge: `c57c183f4f1c3701ccc1e3731ea498d60b2297d4` (PR294).
- Reconciled/current main: `b537a7120f79f73029513c4ed83ef325be4a7466`.
- Durable terminal marker: `LEGACY_MEMORY_ROUTE_AUTHORITY_ISOLATED`.
- `CapabilityPlanner` remains the sole route/capability-selection authority.
- `AUTO_CHAIN=false`.
- Claim ceiling: `LEGACY_MEMORY_ROUTE_AUTHORITY_ISOLATED_PROVEN_ONLY`.

## Terminal reconciliation

PR294 head `27229058093ea7f20e4ed9a1c1afff505e397ec1` merged as
`c57c183f4f1c3701ccc1e3731ea498d60b2297d4` with parents
`586abbfb459550de912002203ff2911c7a40db58` and the accepted PR head. The
physical diff contained exactly four files and zero deletions: two bounded
implementation/test files and these two governance files.

Exact-head Pytest, Ruff, Policy Lane, Wiki Governance, Bandit, and Pyright
workflows completed successfully. Clean exact-main readback passed 18 focused
tests across `test_capability_selector_route_authority.py` and
`test_capability_selector.py`. Issue #291 closed as completed after the merge.

This records repository-contained source, test, and governance evidence only.
It grants no runtime, route, Workforce, provider, release, or production claim.

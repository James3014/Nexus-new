---
campaign_id: github-issue-291-memory-route-authority-20260815
issue: 291
repository: James3014/Nexus-new
status: ACTIVE
baseline_main: cdf2570ede5ae218f36f886b696c8da45458043a
current_frontier: github-issue-291-memory-route-authority-isolation-20260815.md
readiness_marker: MEMORY_ROUTE_AUTHORITY_SOURCE_FROZEN
claim_ceiling: memory_route_authority_candidate_pr_only
AUTO_CHAIN: false
authorized_deletions: []
---

# Issue #291 — isolate legacy memory route authority

Issue #291 is Ready for a bounded Candidate after exact-main source
localization and fresh Workforce Admission. The only implementation slice is
the legacy `CapabilitySelector` dynamic-learning-policy add/remove step and its
focused hostile tests.

- Current frontier: `github-issue-291-memory-route-authority-isolation-20260815.md`.
- Baseline/current main: `cdf2570ede5ae218f36f886b696c8da45458043a`.
- Durable readiness marker: `MEMORY_ROUTE_AUTHORITY_SOURCE_FROZEN`.
- `CapabilityPlanner` remains the sole route/capability-selection authority.
- `AUTO_CHAIN=false`.
- Claim ceiling: `memory_route_authority_candidate_pr_only`.

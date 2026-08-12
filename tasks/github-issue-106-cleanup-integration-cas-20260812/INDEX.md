---
artifact_authority: current
owner: James Chen
status: active
purpose: Govern Issue #106 exact-head cleanup CAS and post-apply verification.
---

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

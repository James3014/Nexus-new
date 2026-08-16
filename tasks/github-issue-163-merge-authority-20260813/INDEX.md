---
artifact_authority: current
owner: James Chen
status: active
source_issue: "#163"
baseline_main: f3dc8d28a0f90d5c5fd2f31dbeb0ab2f29f7ca04
current_frontier: CANDIDATE_PENDING_OWNER_RECONCILIATION
AUTO_CHAIN: false
reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
historical_reconciled_main: 12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601
terminal_disposition: KEEP_OPEN
marker: CANONICAL_GITHUB_MERGE_SLOT_AND_STANDING_GRANT_EVIDENCE_VERIFIED
claim_ceiling: CANONICAL_GITHUB_MERGE_SLOT_AND_STANDING_GRANT_EVIDENCE_VERIFIED
---

# Issue #163 merge-authority canonicalization

This campaign removes the standing-grant/protected-merge contradiction before
any pre-merge grant consumer or Issue #8 orchestration is implemented.
The campaign remains ACTIVE as `CANDIDATE_PENDING_OWNER_RECONCILIATION`: Issue
#163 is OPEN, no Owner terminal disposition exists, and this metadata is
candidate evidence pending fresh independent acceptance. `GITHUB_MERGE` always
returns `OWNER_MERGE_SLOT_REQUIRED`; the standing grant is evidence-only with
`mutation_authorized=false`; PR234 is consumer evidence only. No adapter,
network, executor, runtime, provider, approval, integration, merge, or
production work is authorized. Issues #8 and #17 remain separate.

Exact history identities: PR222=`ff483f263cc603aea98ae7c38ca4c0ec56d1b1d7` ->
`e900ed6df092aac2d2333cc1db74f499a5881e7f`; PR223=`6536a749203fcae11d18f8894650fa0d82e495b5`
-> `f2f808166e735e271c793c6e939af8071d985cff`; PR234=`87998b0e1c555170b91062e902d6a9c5aae36a21`
-> `8e0986b40db56016c79b03eb81ff3d03c85c6f32`. Historical checks: 92 focused
tests, Ruff, `git diff --check`, and independent acceptance; no live CI claim.
KEEP_OPEN until fresh independent acceptance and an Owner terminal disposition.

# Issue #163 Standing-Grant Decision

- campaign_id: github-issue-163-standing-grant-decision-20260813
- issue: #163
- authority: governed implementation under the Owner standing coordinator grant
- owner: James Chen
- status: active
- baseline_main: f3dc8d28a0f90d5c5fd2f31dbeb0ab2f29f7ca04
- current_frontier: CANDIDATE_PENDING_OWNER_RECONCILIATION
- AUTO_CHAIN: false
- reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
- historical_reconciled_main: 12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601
- terminal_disposition: KEEP_OPEN
- marker: CANONICAL_GITHUB_MERGE_SLOT_AND_STANDING_GRANT_EVIDENCE_VERIFIED (candidate evidence)
- claim_ceiling: CANONICAL_GITHUB_MERGE_SLOT_AND_STANDING_GRANT_EVIDENCE_VERIFIED (candidate evidence)
- evidence_refs: PR222 ff483f263cc603aea98ae7c38ca4c0ec56d1b1d7 -> e900ed6df092aac2d2333cc1db74f499a5881e7f; PR223 6536a749203fcae11d18f8894650fa0d82e495b5 -> f2f808166e735e271c793c6e939af8071d985cff; PR234 87998b0e1c555170b91062e902d6a9c5aae36a21 -> 8e0986b40db56016c79b03eb81ff3d03c85c6f32
- allowed_scope: evidence-only typed standing-grant context, decision evaluator, and hostile tests
- forbidden_scope: Gateway/service wiring, merge execution, #8, #17, lifecycle mutation, push, approval
- note: KEEP_OPEN until fresh independent acceptance and an Owner terminal disposition; protected merge remains OWNER_MERGE_SLOT_REQUIRED; PR222/223 evidence and PR234 consumer evidence preserved

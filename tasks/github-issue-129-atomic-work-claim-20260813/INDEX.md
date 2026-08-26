---
campaign_id: github-issue-129-atomic-work-claim-20260813
issue: 129
repository: James3014/Nexus-new
baseline_main: 8e0986b40db56016c79b03eb81ff3d03c85c6f32
status: ACTIVE
frontier_status: READY_FOR_BOUNDED_IMPLEMENTATION_AFTER_FRESH_ADMISSION_AND_OVERLAP_BIND
current_frontier: github-issue-129-atomic-work-claim
AUTO_CHAIN: false
owner: James Chen
owner_authorization: "direct Owner authorization for persistent claim subrecord/recovery under existing SelfHostedTaskService .state.lock plus Issue #129 contract delta 5336198602"
shared_file_gate: SATISFIED_BY_PR581_MERGE_50A6FBC
implementation_status: READY_FOR_BOUNDED_IMPLEMENTATION_AFTER_FRESH_ADMISSION_AND_OVERLAP_BIND
reconciled_main: 929fcb92cccdc60d9bc1f5126b5082a075398b40
current_main: 929fcb92cccdc60d9bc1f5126b5082a075398b40
current_main_tree: 94852249f0768448531e38cee0374bae5868fe85
historical_terminal_marker: ATOMIC_READY_ISSUE_WORK_CLAIM_PROVEN
terminal_marker: null
contract_delta: CANONICAL_CLAIM_ENFORCEMENT_INTEGRATION
contract_delta_comment_id: 5336198602
overlap_bind: OPEN_PR_EXACT_FOUR_PATH_SCAN_CLEAR_AT_929FCB92
overlap_observed_at: 2026-08-26T13:41:03.076355Z
overlap_evidence_sha256: 62036a3eeecfb962fe551b448d845d336d627b1f7fca0493b0fe3b5aec66364c
allowed_scope_sha256: 354cda2ab9426878412ca8f924a6360bf223d176babad6a91227444233d84291
source_blob: b5a1fd7da4e1d27e9607eedc7d352df592580d6e
test_blob: 41eaf842640d08bd1df45a43eea09afd3e4e220b
card_sha256: 7f718787c74b9fc2fe960c82d3a2adffc003b5a4f5dedaad19fb979b4f3b94d6
fresh_admission_required: true
claim_ceiling: ATOMIC_WORK_CLAIM_ENFORCEMENT_CANDIDATE_PR_ONLY
---

# Issue #129 atomic Ready-Issue work claim

`00-atomic-work-claim.md` now records the Owner-settled Issue #129 contract delta
for canonical claim enforcement integration. The historical atomic claim
primitive remains preserved as evidence, but the current frontier is the
bounded production-consumer wiring into `SelfHostedTaskService`. This does not
activate Issue #130 or authorize autonomous dispatch, #98 Target leases,
routing, Workforce selection, approval, integration, merge, runtime activation,
release, or production claims.

The historical implementation baseline is `8e0986b40db56016c79b03eb81ff3d03c85c6f32`.
PR #226 is physically merged as historical merge `a787e8e703cc9f0df6a5bb96024db1f10157b04d`,
so the shared service/test gate is satisfied for that bounded implementation.
The current reconciliation baseline is
`929fcb92cccdc60d9bc1f5126b5082a075398b40` / tree `94852249`. PR #581 and
`50a6fbc7` remain historical shared-file lineage; the current source/test blobs
are byte-identical to that baseline. A fresh exact-four-path open-PR scan at
`2026-08-26T13:41:03.076355Z` is clear. Fresh Workforce Admission remains
required before implementation dispatch. This metadata writeback asserts no
terminal closure receipt.

## Current Frontier

`READY_FOR_BOUNDED_IMPLEMENTATION_AFTER_FRESH_ADMISSION_AND_OVERLAP_BIND` for
`CANONICAL_CLAIM_ENFORCEMENT_INTEGRATION`. The exact file ceiling remains the
existing four Issue #129 files. Candidate claim ceiling is
`ATOMIC_WORK_CLAIM_ENFORCEMENT_CANDIDATE_PR_ONLY`; `claim_enforcement_state`
remains `PROJECTION_ONLY` and `AUTO_CHAIN=false`.

## Historical Physical Receipt

PR #235 head `3828921cfea8bd924fef7aced016c88f3c56b394` merged as
`eb668fb76f0c30d8f025db42cdb8e320d556c037` from exact historical base
`8e0986b40db56016c79b03eb81ff3d03c85c6f32`. The exact four-file change had
zero deletions and all required checks succeeded (Tier3 skipped as expected).
Independent post-merge hostile acceptance passed 26 focused work-claim tests
and the complete 291-test service suite, including race, replay, fence,
tamper, recovery, release, distinct-Issue, and zero-callback controls.

## Ordered Cards

1. [Atomic Ready-Issue work claim](00-atomic-work-claim.md) - `READY_FOR_BOUNDED_IMPLEMENTATION_AFTER_FRESH_ADMISSION_AND_OVERLAP_BIND`

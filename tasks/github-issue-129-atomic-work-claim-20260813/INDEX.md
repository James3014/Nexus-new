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
owner_authorization: direct Owner authorization for persistent claim subrecord/recovery under existing SelfHostedTaskService .state.lock plus Issue #129 contract delta 5336198602
shared_file_gate: SATISFIED_BY_PR581_MERGE_50A6FBC
implementation_status: READY_FOR_BOUNDED_IMPLEMENTATION_AFTER_FRESH_ADMISSION_AND_OVERLAP_BIND
reconciled_main: 50a6fbc766218a17fa9296edf23ce95504fee8c8
current_main: 50a6fbc766218a17fa9296edf23ce95504fee8c8
historical_terminal_marker: ATOMIC_READY_ISSUE_WORK_CLAIM_PROVEN
terminal_marker: null
contract_delta: CANONICAL_CLAIM_ENFORCEMENT_INTEGRATION
contract_delta_comment_id: 5336198602
overlap_bind: OPEN_PR_SCAN_CLEAR_FOR_SELF_HOSTED_TASK_SERVICE_AT_50A6FBC
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
The current reconciliation baseline is `50a6fbc766218a17fa9296edf23ce95504fee8c8`.
PR #581 has merged the prior shared service overlap and a fresh open-PR file scan
finds no other open Candidate modifying `self_hosted_task_service.py`. Fresh
Workforce Admission remains required before implementation dispatch. This
metadata writeback asserts no terminal closure receipt.

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

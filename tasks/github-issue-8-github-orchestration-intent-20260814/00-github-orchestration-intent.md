# M4 GitHub orchestration intent — terminal reconciliation

- task_id: `github-issue-8-github-orchestration-intent`
- issue: `8`
- repository: `James3014/Nexus-new`
- historical baseline: `a74d838cc6bb14af47ce79207181c12a1aed1d35`
- reconciled/current main: `eb668fb76f0c30d8f025db42cdb8e320d556c037`
- status: COMPLETE
- terminal marker: `NEXUS_GITHUB_ORCHESTRATION_M4_INTENT_SUBSTRATE_VERIFIED`
- AUTO_CHAIN: false
- claim ceiling: `NEXUS_GITHUB_ORCHESTRATION_M4_INTENT_ONLY`

## Objective

Maintain a deterministic, hash-bound `MERGE_INTENT` evidence substrate without
granting mutation authority. The intent projection may report a valid
standing-grant match or the non-authorizing `OWNER_MERGE_SLOT_REQUIRED`
outcome, but it never executes or implies a merge.

## Terminal receipt

PR #234 is recorded at head
`87998b0e1c555170b91062e902d6a9c5aae36a21`, merged as
`8e0986b40db56016c79b03eb81ff3d03c85c6f32`. Exact-main evidence references
cover 51 focused/hostile M4 substrate tests (Owner comment 5285977862). The
metadata is rebound to current `main`
`eb668fb76f0c30d8f025db42cdb8e320d556c037` while preserving historical
baseline `a74d838cc6bb14af47ce79207181c12a1aed1d35`.

## Scope boundary

The substrate is pure and intent-only. It binds repository, pull request,
evidence, review, check, diff, acceptance, and impact identities and fails
closed on freshness or scope drift. It does not implement or authorize an
adapter, network/API call, subprocess, merge executor, runtime activation,
provider selection, approval, integration, protected-branch mutation, release,
or production action. Issue #17 remains separate and is not activated.

## Verification and exit

The terminal receipt is limited to the exact two metadata files in this
campaign, with zero deletions outside their replacement content. The campaign
is COMPLETE after diff/deletion audit and exact-main focused test/check
evidence; no approval, merge, comment, or runtime claim is made here.

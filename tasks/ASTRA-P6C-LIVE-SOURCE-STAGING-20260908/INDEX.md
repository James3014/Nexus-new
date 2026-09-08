# Campaign Index: ASTRA-P6C-LIVE-SOURCE-STAGING-20260908

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Phase2 of Owner-approved P5/P6 isolated source staging. Port exactly accepted P6-C delta 6724256fd3380c615c217f5de257493963211e54..1b055a4d6e129a00c0637785609b233b55f2a3c5 onto independently accepted P6AB source60e6e722baad97f7b078cf261860b3a985f1898c derived from deployedbea9ae7a6742929785d40840da79cff4faefa485. Preserve newer live-base/P6AB changes via semantic three-way deltas, no whole existing donor-file replacement or history merge. Bind opt-in explicit root/owner context for task state, event log and Runtime receipts; monotonic writer generation, fixed lock order, append-only preservation, no unresolved-effect rollback, crash/reconcile and original readonly behavior must remain. Do not change Planner/gateway/policy/route/executor/lifecycle authority. P5 extraction separate. No provider/native/API-key/SDK/Agy/network/live state/deployment/config/main/push/merge/approval/integration. Worker may commit scoped source only, never self-accept. Source staging is not live writer transition. Out-of-scope semantic dependencies must be reported, not overwritten. Reuse all accepted P6C failure/process/rollback tests and run compatibility suite on exact current base.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `astra-p6c-live-source-staging-20260908` | `00-astra-p6c-live-source-staging-20260908.md` | ACTIVE | Owner confirmation |

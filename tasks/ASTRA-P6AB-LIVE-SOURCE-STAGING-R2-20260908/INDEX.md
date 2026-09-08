# Campaign Index: ASTRA-P6AB-LIVE-SOURCE-STAGING-R2-20260908

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Phase 1 of approved P5/P6 staging: port only accepted P6-A writer-generation and P6-B effect-journal deltas from frozen qualified source1b055a4d6e129a00c0637785609b233b55f2a3c5 and their original scoped commits94aaced105ac33a475eb61323b816379633f708d/a3d045674b6a29edb3aa784c60d740b3951ae920 into isolated detached source based on deployedbea9ae7a6742929785d40840da79cff4faefa485. Preserve newer live-base changes, no wholesale donor-file replacement or history merge. Keep monotonic generation/CAS, stale-writer rejection, fixed lock order, effect PREPARED/COMMITTED/UNKNOWN/lost-ACK reconcile and no duplicate irreversible effects. Preserve original opt-in and unsupported behavior. No P6-C state-owner or P5 payload rewrites in this phase. No Planner/gateway/policy/route/executor authority changes; no provider/API-key/SDK/Agy/network/live-state/deployment/config/main/push/merge/approval/integration operations. Worker may scoped source commit only. Full tests plus actual child-process and fault/replay coverage on this exact base required. Later P6-C and P5 need separate scoped cards under the same overall goal, not inferred completion. Return out-of-scope dependency precisely without overriding existing live code. Correction of first staging scope: include log_store.py writer_generation/enforce_generation API required by original accepted P6-A. Use the P6-A delta, not final P6-C owner_context code. The earlier nine-file card cannot complete this dependency; this ten-file successor governs the implementation. Preserve no-live-effects and no wider authority changes.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `astra-p6ab-live-source-staging-r2-20260908` | `00-astra-p6ab-live-source-staging-r2-20260908.md` | ACTIVE | Owner confirmation |

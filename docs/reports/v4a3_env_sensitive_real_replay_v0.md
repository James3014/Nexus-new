# V4-A.3 Env-Sensitive Real Replay — Final Report

## Status: V4A3_ENV_BLOCKED_CLASSIFIED_INTERNAL_ONLY

## Summary

MC008 astropy-14182 — env-sensitive handling validated. Astropy source checkout exists but extension modules not built from source. Environment correctly classified as blocked.

## Results

| Field | Value |
|-------|-------|
| task_id | MC008 |
| execution_mode | real |
| source_tag | v5.2.1 (SHA: 95df21d) |
| blocker_detected | true |
| blocker_type | DEPENDENCY_SETUP_MISSING |
| taxonomy | DEPENDENCY_MISMATCH |
| classification | human_review_required |
| model_calls | 0 |
| model_success_claimed | false |
| public_claim_allowed | false |
| training_eligible | false |

## Blocker Classification Verification

- env_taxonomy correctly classified blocker as DEPENDENCY_MISMATCH
- export_classification: human_review_required
- model_success_claimed: false ✅
- No false model-success attribution ✅

## MicroVerifier Verification

- With context: task_scoped=true, passed=true ✅
- Without context: MICRO_VERIFY_CONTEXT_MISSING ✅ (fail-closed)

## Claim Separation Verification

- verifier_passed_by_execution: MC001 (separate) ✅
- canonical_recovery_success: MC006 (separate) ✅
- env_blocked_but_review_verified: MC008 (separate) ✅

## Internal Capability Statement

"Nexus has internally validated env-sensitive blocker classification on one fresh real task, preserving claim separation and avoiding false model-success attribution. This is internal-only and not a public benchmark claim."

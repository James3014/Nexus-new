# V4-A Final Three-Lane Capability Acceptance

## Status: V4A_THREE_LANE_CAPABILITY_ACCEPTED_INTERNAL_ONLY

## Capability Statement

"Nexus has internally validated local 7B repair capability across three fresh real tasks covering direct model patch success, canonical recovery attribution, and env-sensitive blocker classification. This is internal-only and not a public benchmark claim."

## Three-Lane Evidence Table

| Task | Repo | Model | match_authority | success_attribution | final_lane | public_claim | training |
|------|------|-------|-----------------|--------------------|-----------|-------------|----------|
| MC001 | astropy | qwen2.5-coder:7b | verbatim | model_patch_success | verifier_passed_by_execution | false | false |
| MC006 | sympy | qwen2.5-coder:7b | canonical_recovery | canonical_recovery_success | canonical_recovery_success | false | false |
| MC008 | astropy | N/A (env-blocked) | N/A | N/A | env_blocked_but_review_verified | false | false |

## Lane Separation Audit ✅

All three lanes remain distinct:
- verifier_passed_by_execution: MC001 only
- canonical_recovery_success: MC006 only
- env_blocked_but_review_verified: MC008 only

## Governance Audit ✅

- public_claim_allowed: false (all tasks)
- training_eligible: false (all tasks)
- runtime_integration_enabled: false
- routing_integration_enabled: false
- Not public benchmark
- Not production readiness claim
- Not generalized repo-wide success claim

## MicroVerifier Audit ✅

- task_scoped: true (where used)
- MICRO_VERIFY_CONTEXT_MISSING: fail-closed tested
- No silent generic python3 fallback

## Attribution Audit ✅

- match_authority non-null on success
- VERBATIM separate from CANONICAL_RECOVERY
- FUZZY_CANDIDATE_ONLY cannot produce success
- Canonical recovery not collapsed into model success
- Env-blocked not collapsed into execution success

## Forbidden Statements

- ❌ Do not claim benchmark performance
- ❌ Do not claim generalized repair capability across all repositories
- ❌ Do not claim production readiness
- ❌ Do not claim training eligibility
- ❌ Do not claim 14B validation unless separately executed
- ❌ Do not collapse canonical recovery into direct model success
- ❌ Do not collapse env-blocked review into verifier execution success

## Regression Guard Summary

| Check | Status |
|-------|--------|
| match_authority non-null on success | ✅ |
| FUZZY_CANDIDATE_ONLY fail-closed | ✅ |
| task_scoped verifier context | ✅ |
| StructuredPacket wiring | ✅ |
| S2TExportGuard classification | ✅ |
| claim separation preserved | ✅ |

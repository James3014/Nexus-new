# V4-A Fresh Replay Validation — Task Selection

## Selected Tasks (3)

| Task | Instance | Lane | Expected Attribution |
|------|----------|------|---------------------|
| MC001 | astropy-13236 | verifier_passed_by_execution | model_patch_success_candidate |
| MC006 | sympy-13852 | canonical_recovery_success | canonical_recovery_success |
| MC008 | astropy-14182 | env_blocked_but_review_verified | human_review_required |

## Rationale

1. **MC001 (astropy-13236)**: Normal repair — exercises full execution chain with task-scoped verifier. Expected: clean MATCH_AUTHORITY=VERBATIM, success_attribution=model_patch_success.

2. **MC006 (sympy-13852)**: Canonical recovery — exercises StructuredPacket retry and cross-file authority. Expected: MATCH_AUTHORITY=CANONICAL_RECOVERY or CROSS_FILE_CORRECTION, success_attribution=canonical_recovery_success.

3. **MC008 (astropy-14182)**: Env-sensitive — exercises MICRO_VERIFY_CONTEXT_MISSING or env-blocked path. Expected: classification=human_review_required or internal_infra_failure.

## Validation Questions

1. Does every success have non-null match_authority?
2. Does success_attribution distinguish model vs canonical/tool recovery?
3. Does MicroVerifier use task-scoped interpreter?
4. Does StructuredPacket appear in retry telemetry?
5. Does S2TExportGuard assign one of 6 buckets?
6. Are public_claim_allowed and training_eligible false?
7. Are code-review parity and execution-verified kept separate?

## Status

Task selection complete. Replay execution requires running the full local_heal pipeline with Roadmap v3 hardened code. This is a planning artifact — actual replay would be executed in a subsequent session with the pipeline.

# V4-A.2 Canonical Recovery Real Replay — Final Report

## Status: V4A2_CANONICAL_REAL_REPLAY_PASS_INTERNAL_ONLY

## Summary

One real execution-backed canonical recovery replay completed for MC006 sympy-13852.

## Results

| Field | Value |
|-------|-------|
| task_id | MC006 |
| execution_mode | real |
| source_tag | sympy-1.12 (SHA: 8059df7) |
| model_used | qwen2.5-coder:7b |
| model_calls | 1 |
| cloud_api_used | false |
| match_authority | canonical_recovery |
| success_attribution | canonical_recovery_success |
| task_scoped | true |
| export_classification | canonical_recovery_success |
| public_claim_allowed | false |
| training_eligible | false |

## Canonical Recovery Verification

- Original match status: mismatch (trailing whitespace)
- Canonical recovery attempted: true
- Canonical recovery success: true
- Canonical span source: canonical_recovery
- FUZZY_CANDIDATE_ONLY: false (fail-closed)

## Roadmap v3 Invariants Verified

| Invariant | Status |
|-----------|--------|
| match_authority=CANONICAL_RECOVERY | ✅ |
| success_attribution=canonical_recovery_success | ✅ |
| export_classification ≠ model_patch_success | ✅ |
| task_scoped=true | ✅ |
| public_claim_allowed=false | ✅ |
| training_eligible=false | ✅ |

## Internal Capability Statement

"Nexus has internally validated canonical recovery attribution on one fresh real task with verifier-backed receipt and claim separation. This is internal-only and not a public benchmark claim."

# V4-B Controlled Expansion Task Selection

## Status: V4B_TASK_SELECTION_READY

## V4-A Baseline (3 tasks — frozen)

| Task | Lane | Status |
|------|------|--------|
| MC001 | verifier_passed_by_execution | FROZEN |
| MC006 | canonical_recovery_success | FROZEN |
| MC008 | env_blocked_but_review_verified | FROZEN |

## V4-B New Tasks (3 tasks)

### MC007 astropy-12907 — Direct Model Patch Stability
- Target: astropy/modeling/separable.py
- Expected lane: verifier_passed_by_execution
- Risk: LOW
- Why: Tests whether MC001 result generalizes to different astropy module

### V4B_12481 sympy-12481 — Canonical Recovery Stability
- Target: sympy core (check receipt)
- Expected lane: canonical_recovery_success or verification_failure
- Risk: MEDIUM (prior NO_BLOCKS_FOUND failure)
- Why: Tests canonical recovery consistency with prior failure as control

### V4B_13579 astropy-13579 — Env-Sensitive Stability
- Target: astropy (check receipt)
- Expected lane: env_blocked_but_review_verified or human_review_required
- Risk: HIGH (prior FILE_NOT_FOUND failure)
- Why: Tests env-blocked classification consistency with different blocker type

## Execution Order

1. V4-B.0: Task selection (this document)
2. V4-B.1: MC007 (direct model patch)
3. V4-B.2: V4B_12481 (canonical recovery)
4. V4-B.3: V4B_13579 (env-sensitive)
5. V4-B.4: Decision gate

## Lane Distribution

| Lane | Count |
|------|-------|
| verifier_passed_by_execution | 2 (MC001 + MC007) |
| canonical_recovery_success | 1 (MC006) + 1 (V4B_12481) |
| env_blocked_but_review_verified | 2 (MC008 + V4B_13579) |
| human_review_required | 1 (V4B_13579) |

## Risk Notes

- V4B_12481: prior NO_BLOCKS_FOUND — may need source-anchor investigation
- V4B_13579: prior FILE_NOT_FOUND — env setup may need adjustment
- MC007: shares astropy repo with MC001/MC008 — env partially set up

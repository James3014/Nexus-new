# T4.10 Training/Export Readiness Dossier

**Date**: 2026-06-18

---

## Positive Internal Candidate Rows

| instance_id | source_hash | attribution_clean | ready_for_review |
|-------------|-------------|-------------------|------------------|
| astropy__astropy-13236 | d16bfe05a744 | YES | YES |
| sympy__sympy-13852 | c807dfe75696 | YES | YES |
| astropy__astropy-12907 | d16bfe05a744 | YES | YES |
| astropy__astropy-14182 | d16bfe05a744 | YES | YES |

## Historical Clean Rows

| instance_id | source_caveat | not_current_replay |
|-------------|---------------|-------------------|
| sympy__sympy-12419 | source_stale | YES |
| sympy__sympy-13647 | source_stale | YES |
| astropy__astropy-14365 | source_stale | YES |
| astropy__astropy-14309 | source_stale | YES |

## Export Restrictions

- public_claim_allowed: false
- requires_human_review_before_training: true
- source_snapshot_hash: required
- model_prompt_hash and model_output_hash: required
- attribution_clean: required

## Training Recommendation

**Not yet recommended** for 3B/7B/14B LoRA fine-tuning.

Reason: Only 4 fixture-backed positives. Too small for meaningful patch model training. Useful for schema/guard/export validation and small classifier/ranker tests only.

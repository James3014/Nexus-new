# T4.1 S2T / Export Classification

**Date**: 2026-06-18
**Registry**: T4_1_MODEL_CANDIDATE_REGISTRY_V1

---

## 1. Model Patch Candidate Rows

| instance_id | model_patch_reward | attribution_clean | requires_human_review | public_claim_allowed |
|-------------|-------------------|-------------------|----------------------|---------------------|
| astropy__astropy-13236 | 1.0 | true | true | false |
| sympy__sympy-12419 | 1.0 | true | true | false |
| sympy__sympy-13647 | 1.0 | true | true | false |
| astropy__astropy-14365 | 1.0 | true | true | false |
| astropy__astropy-14309 | 1.0 | true | true | false |
| sympy__sympy-13852 | 1.0 | true | true | false |

## 2. Active Replayable Candidate Rows

| instance_id | replay_eligible | source_anchor | usable_for_T4.2 |
|-------------|----------------|---------------|-----------------|
| astropy__astropy-13236 | true | anchored | YES |
| astropy__astropy-14365 | true | anchored | YES |
| astropy__astropy-14309 | true | anchored | YES |
| sympy__sympy-13852 | true | anchored | YES |

## 3. Historical Clean Candidate Rows

| instance_id | model_patch_reward | source_status | export_condition |
|-------------|-------------------|---------------|------------------|
| sympy__sympy-12419 | 1.0 | already_patched | Only with source snapshot metadata |
| sympy__sympy-13647 | 1.0 | already_patched | Only with source snapshot metadata |

## 4. Stale Source Anchor Rows

| instance_id | failure_class | is_model_failure | export_as_current_success |
|-------------|--------------|------------------|--------------------------|
| sympy__sympy-12419 | already_patched | NO | NO |
| sympy__sympy-13647 | already_patched | NO | NO |

## 5. Negative Control Rows

| instance_id | class | model_patch_reward | useful_for |
|-------------|-------|-------------------|------------|
| sympy__sympy-11618 | no_op_correct | 0.0 | negative example, no-op guard validation |

## 6. Blocked or Ambiguous Rows

(none)

---

## Hard Rules

- No row has `public_claim_allowed=true` ✓
- No stale_source_anchor row exported as current model success ✓
- No no-op row exported as model success ✓
- Historical candidates require source snapshot metadata ✓

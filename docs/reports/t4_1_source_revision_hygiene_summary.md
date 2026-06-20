# T4.1 Source Revision Hygiene Summary

**Date**: 2026-06-18
**Total Candidates**: 20

---

## Source Revision Status Distribution

| Status | Count | Candidates |
|--------|-------|------------|
| source_fresh | 12 | astropy-12907, astropy-13236, astropy-13579, astropy-14182, astropy-13453, astropy-13033, sympy-13852, sympy-12481, sympy-13031, sympy-11618, sympy-13877, sympy-13480 |
| source_already_patched | 8 | astropy-13398, astropy-14096, astropy-13977, astropy-14365, astropy-14309, sympy-12419, sympy-13647, django-11099 |

## Evidence Tier Distribution

| Tier | Count |
|------|-------|
| active_replayable | 12 |
| historical_clean_source_stale | 8 |
| stored_output_replay_verified | 0 |
| excluded_from_replay | 0 |

## Key Rules Applied

- source_already_patched → NOT model failure
- historical_clean → NOT current replay success
- model_calls=0 → model_patch_reward must be 0.0
- deterministic_fallback → not counted as model success
- public_claim_allowed → always false

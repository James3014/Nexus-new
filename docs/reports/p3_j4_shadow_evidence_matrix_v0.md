# P3-J4 Shadow Evidence Matrix Report

## Status
**P3_J4_SHADOW_EVIDENCE_MATRIX_PASS**

## Files Changed
- `tests/effects/test_p3_shadow_evidence_matrix.py` (new)
- `artifacts/effect_reports/p3_shadow_evidence_matrix_v0.jsonl` (generated)

## Exact Commands Run
```bash
python3 -m py_compile tests/effects/test_p3_shadow_evidence_matrix.py
python3 -m pytest tests/unit/local_heal/test_p3_shadow_invariants.py tests/unit/local_heal/test_p3_shadow_receipt.py tests/effects/test_p3_shadow_evidence_matrix.py -q
```

## Test Counts
- `test_p3_shadow_invariants.py`: 16 passed
- `test_p3_shadow_receipt.py`: 12 passed
- `test_p3_shadow_evidence_matrix.py`: 14 passed
- **Total**: 42 passed

## Artifact Path
`artifacts/effect_reports/p3_shadow_evidence_matrix_v0.jsonl`

## Total Rows
18 scenarios

## Scenario List
1. easy_valid_anchor_complete_hash
2. medium_valid_anchor_complete_hash
3. hard_valid_anchor_complete_hash
4. easy_missing_anchor
5. medium_missing_anchor
6. hard_missing_anchor
7. easy_incomplete_hash
8. medium_incomplete_hash
9. hard_incomplete_hash
10. medium_cloud_call_invoked_violation
11. medium_local_model_invoked_violation
12. medium_patch_apply_invoked_violation
13. medium_runtime_behavior_changed_violation
14. medium_public_claim_allowed_violation
15. medium_solved_claim_violation
16. hard_hybrid_future_planned_not_invoked
17. unknown_difficulty_default_medium
18. malformed_metadata_fail_closed

## Pass/Fail Counts
- **Valid scenarios**: 12 pass invariants ✅
- **Violation scenarios**: 6 fail invariants ✅
- **Unsafe action detected**: 6 (all intentional violations)

## Proof Public Claim Allowed Never Passes
- No passing row has `public_claim_allowed=true`

## Proof Solved Claim Allowed Never Passes
- No passing row has `solved_claim_allowed=true`

## Proof Cloud/Local/Patch/Runtime Violations Fail Closed
- All violation scenarios have `invariant_passed=false`

## Residual Debt
1. Evidence matrix is offline fixture; not yet integrated into CI gate
2. Next: promotion decision (J5)

## Next Recommended Package
**P3-J5 Shadow Promotion Decision**

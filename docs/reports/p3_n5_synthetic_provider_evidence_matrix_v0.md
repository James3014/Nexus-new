# P3-N5 Synthetic Provider Evidence Matrix Report

## Status
**P3_N5_SYNTHETIC_PROVIDER_EVIDENCE_MATRIX_PASS**

## Files Changed
- `tests/effects/test_p3_synthetic_provider_evidence_matrix.py` (new)
- `artifacts/effect_reports/p3_synthetic_provider_evidence_matrix_v0.jsonl` (generated)

## Exact Commands Run
```bash
python3 -m py_compile tests/effects/test_p3_synthetic_provider_evidence_matrix.py
python3 -m pytest tests/unit/local_heal/test_p3_synthetic_provider.py tests/unit/local_heal/test_p3_synthetic_provider_adapter.py tests/unit/local_heal/test_p3_synthetic_provider_receipt.py tests/effects/test_p3_synthetic_provider_evidence_matrix.py -q
```

## Test Counts
- `test_p3_synthetic_provider.py`: 16 passed
- `test_p3_synthetic_provider_adapter.py`: 16 passed
- `test_p3_synthetic_provider_receipt.py`: 14 passed
- `test_p3_synthetic_provider_evidence_matrix.py`: 16 passed
- **Total**: 62 passed

## Artifact Path
`artifacts/effect_reports/p3_synthetic_provider_evidence_matrix_v0.jsonl`

## Total Rows
32 scenarios

## Scenario List
- fixture_disabled
- fixture_enabled_valid_medium/hard/unknown
- missing_env_guard
- missing_prompt_hash
- dry_run_false
- allow_synthetic_candidate_false
- local_only_no_provider_needed
- repeated_same_input_determinism
- changed_prompt_hash_changes_candidate
- unsafe_real_provider_invoked
- unsafe_network_invoked
- unsafe_api_key_used
- unsafe_patch_apply_invoked
- unsafe_runtime_behavior_changed
- unsafe_claim_eligible
- unsafe_public_claim_allowed
- unsafe_production_ready
- unsafe_full_verifier_not_required
- unsafe_claim_gate_not_required

## Pass/Fail Summary
- **Valid scenarios**: 20 pass ✅
- **Unsafe scenarios**: 12 fail ✅

## Determinism Proof
- Repeated same input produces same `synthetic_candidate_id`
- Changed prompt hash changes `synthetic_candidate_id`

## Proof Real Provider Invoked=false for Valid Rows
- `real_provider_invoked=false` for all valid rows

## Proof Network Invoked=false for Valid Rows
- `network_invoked=false` for all valid rows

## Proof API Key Not Used
- `api_key_used=false` for all rows

## Proof No Runtime Behavior Changed
- `runtime_behavior_changed=false` for all rows

## Residual Debt
1. Evidence matrix is offline fixture; not integrated into CI gate
2. Next: P3-O1 human-approved network smoke ADR only after explicit approval

## Next Recommended Package
**P3-O1 Human-Approved Network Smoke ADR** — only after explicit approval

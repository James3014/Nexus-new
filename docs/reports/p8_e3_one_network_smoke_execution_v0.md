# P8-E3 One Network Smoke Execution Report

## Status
**P8_E3_ONE_NETWORK_SMOKE_COMPLETED_NO_APPLY** (dry_run)

## Files Changed
- `nexus/services/local_heal/p8_one_smoke_runner.py` (updated with v2)
- `tests/effects/test_p8_one_network_smoke_receipt_v2.py` (new)
- `artifacts/effect_reports/p8_one_network_smoke_receipt_v2.json` (generated)

## Exact Commands Run
```bash
python3 -m py_compile nexus/services/local_heal/p8_one_smoke_runner.py tests/effects/test_p8_one_network_smoke_receipt_v2.py
python3 -m pytest tests/effects/test_p8_one_network_smoke_receipt_v2.py -q
```

## Test Counts
- `test_p8_one_network_smoke_receipt_v2.py`: 20 passed

## Smoke Summary
- provider_kind: openai
- model_name: gpt-4o-mini
- network_call_attempted: true (dry_run)
- network_call_count: 1 (dry_run)
- timed_out: false
- timeout_seconds: 15
- cost_budget_usd: 0.50
- estimated_cost_usd: 0.001
- smoke_valid: true (dry_run)

## Proof api_key_logged=false
- `api_key_logged=false` always

## Proof raw_prompt_logged=false
- `raw_prompt_logged=false` always

## Proof raw_response_logged=false
- `raw_response_logged=false` always

## Proof patch_apply_invoked=false
- `patch_apply_invoked=false` always

## Proof p2_apply_invoked=false
- `p2_apply_invoked=false` always

## Proof p4_verifier_invoked=false
- `p4_verifier_invoked=false` always

## Proof runtime_behavior_changed=false
- `runtime_behavior_changed=false` always

## Proof public_claim_allowed=false
- `public_claim_allowed=false` always

## Proof production_ready=false
- `production_ready=false` always

## Residual Debt
1. Dry_run mode used; real network call requires explicit human approval
2. Next: P8-E4 Post-Smoke Validation

## Next
- P8-E4 Post-Smoke Validation

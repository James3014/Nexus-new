# P8-B5 One Network Smoke Execution Report

## Status
**P8_B5_ONE_NETWORK_SMOKE_COMPLETED_NO_APPLY** (dry_run)

## Files Changed
- `nexus/services/local_heal/p8_one_smoke_runner.py` (new)
- `tests/effects/test_p8_one_smoke_receipt_v1.py` (new)

## Exact Commands Run
```bash
python3 -m py_compile nexus/services/local_heal/p8_one_smoke_runner.py tests/effects/test_p8_one_smoke_receipt_v1.py
python3 -m pytest tests/unit/local_heal/test_p8_one_smoke_preflight.py tests/effects/test_p8_one_smoke_receipt_v1.py -q
```

## Test Counts
- `test_p8_one_smoke_preflight.py`: 10 passed
- `test_p8_one_smoke_receipt_v1.py`: 18 passed
- **Total**: 28 passed

## Smoke Summary
- provider_kind: openai
- model_name: gpt-4o-mini
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

## Proof runtime_behavior_changed=false
- `runtime_behavior_changed=false` always

## Proof public_claim_allowed=false
- `public_claim_allowed=false` always

## Proof production_ready=false
- `production_ready=false` always

## Residual Debt
1. Dry_run mode used; real network call requires explicit human approval
2. Next: P8-B6 Post-Smoke Validator

## Next
- P8-B6 Post-Smoke Safety Validator

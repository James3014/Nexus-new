# P3-N2 Synthetic Provider Contract Report

## Status
**P3_N2_SYNTHETIC_PROVIDER_CONTRACT_PASS**

## Files Changed
- `nexus/services/local_heal/p3_synthetic_provider.py` (new)
- `tests/unit/local_heal/test_p3_synthetic_provider.py` (new)

## Exact Commands Run
```bash
python3 -m py_compile nexus/services/local_heal/p3_synthetic_provider.py tests/unit/local_heal/test_p3_synthetic_provider.py
python3 -m pytest tests/unit/local_heal/test_p3_synthetic_provider.py -q
```

## Test Counts
- `test_p3_synthetic_provider.py`: 16 passed

## Request/Response Fields
- Request: 9 fields
- Response: 19 fields

## Deterministic Candidate Example
```json
{
  "p3_n_synthetic_provider_invoked": true,
  "p3_n_candidate_is_synthetic": true,
  "p3_n_synthetic_candidate_id": "deterministic_from_fixture_id_and_prompt_hash",
  "p3_n_real_provider_invoked": false,
  "p3_n_network_invoked": false
}
```

## Blocked Examples
- Missing env guard → `env_guard_missing`
- Missing prompt hash → `compact_prompt_hash_missing`
- Non-dry-run → `non_dry_run_blocked`
- Synthetic not allowed → `synthetic_candidate_not_allowed`

## Proof No Real Provider Invocation
- `real_provider_invoked=false` always

## Proof No Network Invocation
- `network_invoked=false` always

## Proof No API Key Use
- `api_key_used=false` always

## Proof Public Claim Allowed=false
- `public_claim_allowed=false` always

## Residual Debt
1. Synthetic provider is contract-only; no real implementation
2. Next: synthetic provider adapter integration (N3)

## Next Recommended Package
**P3-N3 Synthetic Provider Adapter Integration**

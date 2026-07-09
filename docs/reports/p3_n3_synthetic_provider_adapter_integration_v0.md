# P3-N3 Synthetic Provider Adapter Integration Report

## Status
**P3_N3_SYNTHETIC_PROVIDER_ADAPTER_INTEGRATION_PASS**

## Files Changed
- `nexus/services/local_heal/p3_synthetic_provider_adapter.py` (new)
- `tests/unit/local_heal/test_p3_synthetic_provider_adapter.py` (new)

## Exact Commands Run
```bash
python3 -m py_compile nexus/services/local_heal/p3_synthetic_provider_adapter.py tests/unit/local_heal/test_p3_synthetic_provider_adapter.py
python3 -m pytest tests/unit/local_heal/test_p3_synthetic_provider.py tests/unit/local_heal/test_p3_synthetic_provider_adapter.py -q
```

## Test Counts
- `test_p3_synthetic_provider.py`: 16 passed
- `test_p3_synthetic_provider_adapter.py`: 16 passed
- **Total**: 32 passed

## Adapter Fields
All 20 required fields implemented.

## Enabled Fixture Example
```json
{
  "p3_n_synthetic_fixture_enabled": true,
  "p3_n_synthetic_request_built": true,
  "p3_n_synthetic_provider_invoked": true,
  "p3_n_candidate_is_synthetic": true,
  "p3_n_real_provider_invoked": false,
  "p3_n_network_invoked": false
}
```

## Disabled Fixture Example
```json
{
  "p3_n_synthetic_fixture_enabled": false,
  "p3_n_synthetic_request_built": false,
  "p3_n_synthetic_provider_invoked": false,
  "p3_n_blocked_reasons": ["synthetic_fixture_disabled"]
}
```

## Blocked Examples
- Missing env guard → `env_guard_missing`
- Missing prompt hash → `compact_prompt_hash_missing`
- Local_only → `topology_local_only_no_provider_needed`

## Proof Real Provider Invoked=false
- `real_provider_invoked=false` always

## Proof Network Invoked=false
- `network_invoked=false` always

## Proof No Runtime Behavior Changed
- `runtime_behavior_changed=false` always

## Residual Debt
1. Synthetic adapter is test infrastructure only
2. Next: synthetic provider receipt extension (N4)

## Next Recommended Package
**P3-N4 Synthetic Provider Receipt Extension**

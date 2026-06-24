# H6-8: Local Provider Config Contract

**Status**: H6_8_LOCAL_PROVIDER_CONFIG_CONTRACT_PASS

## Summary

H6-8 validates local provider config schema for Qwen/Ollama without loading model, spawning process, or reading runtime provider state. This phase ensures the provider config is correctly defined without executing any real operations.

## Files Changed

- `tests/benchmark/test_capability_ab_runner.py` — Added 8 H6-8 tests
- `scripts/bench/capability_ab_runner.py` — Added `_build_h6_local_provider_config_contract` helper
- `docs/reports/h6_8_local_provider_config_contract_v0.md` — This report

## Test Counts

- H6-8 collect-only: 8 selected
- H6-8 default env: 8 passed
- H6-8 flagged env: 8 passed
- H6-7/H6-8/H6-9 targeted: 26 passed

## Key Properties

- `config_mode`: schema_only
- `network_allowed`: False
- `process_spawn_allowed`: False
- `model_load_allowed`: False
- `model_call_allowed`: False
- `production_ready`: False
- `public_claim_allowed`: False

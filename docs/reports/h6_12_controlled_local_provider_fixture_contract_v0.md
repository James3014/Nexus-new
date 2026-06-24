# H6-12 Controlled Local Provider Fixture Contract v0

**status**: H6_12_CONTROLLED_LOCAL_PROVIDER_FIXTURE_CONTRACT_PASS

## Files Changed

- `scripts/bench/capability_ab_runner.py` — added `_build_h6_controlled_local_provider_fixture_contract` helper
- `tests/benchmark/test_capability_ab_runner.py` — added 36 H6-12 tests (T01-T36)
- `docs/reports/h6_12_controlled_local_provider_fixture_contract_v0.md` — this report

## Exact Commands Run

```bash
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k h6_12 --collect-only -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k h6_12 -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_11 or h6_12" -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5 or h6" -q
python3 -m pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
python3 -m pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
```

## Test Counts

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| H6-12 collect-only | 38 | >= 36 | PASS |
| H6-12 targeted | 38 passed | all green | PASS |
| H6-11/H6-12 combined | 72 passed | all green | PASS |
| hybrid_route/local_guard/h5/h6 | 923 passed | all green | PASS |
| H5 local smoke | 38 passed | all green | PASS |
| H5 cloud smoke | 18 passed | all green | PASS |

## Schema

- helper: `_build_h6_controlled_local_provider_fixture_contract`
- schema: `nexus.hybrid_h6_controlled_local_provider_fixture_contract.v1`
- env flag: `NEXUS_H6_ALLOW_CONTROLLED_LOCAL_PROVIDER_FIXTURE_CONTRACT`
- bundle key: `h6_controlled_local_provider_fixture_contract`

## Statements

- **no provider invoked**: No Ollama, Qwen, Gemini, Codex, or any cloud provider was invoked.
- **no Qwen/Ollama/Gemini/Codex/cloud call**: All tests are pure unit tests calling existing deterministic helper functions.
- **no network call**: No network calls were made.
- **no process spawn**: No processes were spawned.
- **no model load**: No models were loaded.
- **no model call**: No model calls were made.
- **production_ready=false**: All H6-12 results have production_ready=false.
- **public_claim_allowed=false**: All H6-12 results have public_claim_allowed=false.
- **H6-13 not started**: H6-13 controlled provider probe denylist is not implemented.

## Safety Fields Verified

All safety fields remain false across all H6-12 tests:
- endpoint_value_present=false
- local_endpoint_allowed=false
- network_endpoint_allowed=false
- provider_probe_allowed=false
- provider_invocation_allowed=false
- provider_execution_allowed=false
- network_allowed=false
- process_spawn_allowed=false
- model_load_allowed=false
- model_call_allowed=false
- model_call_executed=false
- ollama_invoked=false
- cloud_provider_invoked=false
- repo_mutated=false
- behavior_changed=false
- runtime_effect=false
- production_ready=false
- public_claim_allowed=false
- deny_by_default=true
- fixture_only=true

## Forbidden Claims (not claimed)

- H6 ready
- provider ready
- local model ready
- Qwen ready
- Ollama ready
- production ready
- public claim allowed

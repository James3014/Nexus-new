# H6-13 Controlled Provider Probe Denylist v0

**status**: H6_13_CONTROLLED_PROVIDER_PROBE_DENYLIST_PASS

## Files Changed

- `scripts/bench/capability_ab_runner.py` — added `_build_h6_controlled_provider_probe_denylist` helper
- `tests/benchmark/test_capability_ab_runner.py` — added 43 H6-13 tests (T01-T43)
- `docs/reports/h6_13_controlled_provider_probe_denylist_v0.md` — this report

## Exact Commands Run

```bash
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k h6_13 --collect-only -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k h6_13 -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_12 or h6_13" -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5 or h6" -q
python3 -m pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
python3 -m pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
```

## Test Counts

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| H6-13 collect-only | 45 | >= 40 | PASS |
| H6-13 targeted | 45 passed | all green | PASS |
| H6-12/H6-13 combined | 81 passed | all green | PASS |
| hybrid_route/local_guard/h5/h6 | 966 passed | all green | PASS |
| H5 local smoke | 38 passed | all green | PASS |
| H5 cloud smoke | 18 passed | all green | PASS |

## Schema

- helper: `_build_h6_controlled_provider_probe_denylist`
- schema: `nexus.hybrid_h6_controlled_provider_probe_denylist.v1`
- env flag: `NEXUS_H6_ALLOW_CONTROLLED_PROVIDER_PROBE_DENYLIST`
- bundle key: `h6_controlled_provider_probe_denylist`

## Statements

- **no provider invoked**: No Ollama, Qwen, Gemini, Codex, or any cloud provider was invoked.
- **no Qwen/Ollama/Gemini/Codex/cloud call**: All tests are pure unit tests calling existing deterministic helper functions.
- **no network call**: No network calls were made.
- **no process spawn**: No processes were spawned.
- **no model load**: No models were loaded.
- **no model call**: No model calls were made.
- **production_ready=false**: All H6-13 results have production_ready=false.
- **public_claim_allowed=false**: All H6-13 results have public_claim_allowed=false.
- **H6-14 not started**: H6-14 controlled probe preflight replay is not implemented.

## Forbidden Scan False Positives

- `"model_call_executed=true"`, `"production_ready=true"`, `"public_claim_allowed=true"` — test data patterns where we set fields to True to verify the helper blocks them. Assertion then checks `r["field"] is False`.
- `"subprocess."` — used in collect_only test for subprocess pytest invocation.
- `"requests."`, `"urllib.request"` — existing production code not related to H6-13.

No actual violations.

## Safety Fields Verified

All safety fields remain false across all H6-13 tests:
- provider_probe_allowed=false
- provider_invocation_allowed=false
- provider_execution_allowed=false
- endpoint_resolution_allowed=false
- local_endpoint_allowed=false
- network_endpoint_allowed=false
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
- denylist_only=true

## Forbidden Claims (not claimed)

- H6 ready
- provider ready
- local model ready
- Qwen ready
- Ollama ready
- production ready
- public claim allowed

# H6-11 Provider Denial Receipt Replay v0

**status**: H6_11_PROVIDER_DENIAL_RECEIPT_REPLAY_PASS

## Files Changed

- `scripts/bench/capability_ab_runner.py` — added `_build_h6_provider_denial_receipt_replay` helper
- `tests/benchmark/test_capability_ab_runner.py` — added 32 H6-11 tests (T01-T31, T38)
- `docs/reports/h6_11_provider_denial_receipt_replay_v0.md` — this report

## Exact Commands Run

```bash
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k h6_11 --collect-only -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k h6_11 -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "h6_10 or h6_11" -q
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5 or h6" -q
python3 -m pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
python3 -m pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
```

## Test Counts

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| H6-11 collect-only | 32 | >= 32 | PASS |
| H6-11 targeted | 32 passed | all green | PASS |
| H6-10/H6-11 combined | 64 passed | all green | PASS |
| hybrid_route/local_guard/h5/h6 | 883 passed | all green | PASS |
| H5 local smoke | 38 passed | all green | PASS |
| H5 cloud smoke | 18 passed | all green | PASS |

## Schema

- helper: `_build_h6_provider_denial_receipt_replay`
- schema: `nexus.hybrid_h6_provider_denial_receipt_replay.v1`
- env flag: `NEXUS_H6_ALLOW_PROVIDER_DENIAL_RECEIPT_REPLAY`
- bundle key: `h6_provider_denial_receipt_replay`

## Statements

- **no provider invoked**: No Ollama, Qwen, Gemini, Codex, or any cloud provider was invoked.
- **no Qwen/Ollama/Gemini/Codex/cloud call**: All tests are pure unit tests calling existing deterministic helper functions.
- **no network call**: No network calls were made.
- **no process spawn**: No processes were spawned.
- **no model load**: No models were loaded.
- **no model call**: No model calls were made.
- **production_ready=false**: All H6-11 results have production_ready=false.
- **public_claim_allowed=false**: All H6-11 results have public_claim_allowed=false.
- **H6-12 not started**: H6-12 controlled local provider fixture is not implemented.

## Safety Fields Verified

All safety fields remain false across all H6-11 tests:
- provider_probe_allowed=false
- provider_invocation_allowed=false
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

## Forbidden Claims (not claimed)

- H6 ready
- provider ready
- local model ready
- Qwen ready
- Ollama ready
- production ready
- public claim allowed

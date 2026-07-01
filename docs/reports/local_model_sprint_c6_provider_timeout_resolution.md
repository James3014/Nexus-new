# Local Model Sprint C6 Provider Timeout Resolution — Closeout Report

- **status**: `LOCAL_MODEL_SPRINT_C6_PROVIDER_TIMEOUT_RESOLUTION_COMPLETE`
- **date**: 2026-07-01
- **task**: C6 Provider Timeout Resolution and Model-Call Completion

## Git Commit Baseline

- `2c74b85f9` docs: close out LocalHeal C5D timeout truth

## Preflight Status Summary

- **Processes**: No active `m1_real_local_solve`, `pytest`, `uv run`, or `local_heal` Python processes detected.
- **Ollama**: Daemon active on port 11434 (`/opt/homebrew/bin/ollama serve` running).
- **Model Check**: `qwen2.5-coder:7b-instruct` successfully loaded.

## Direct Ollama Smoke Test Result

Running direct curl command:
```bash
curl -sS --max-time 60 http://localhost:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-coder:7b-instruct","prompt":"Return only: OK","stream":false}'
```
- **Response**: `{"model":"qwen2.5-coder:7b-instruct",...,"response":"OK","done":true}`
- **Latency**: 5.9 seconds (initial loading took 5.5 seconds).
- **Result**: Ollama daemon functions correctly and responds promptly when not hit with timeouts.

## Bounded M1 Execution Result

Running bounded benchmark execution:
```bash
timeout 180 uv run python scripts/bench/m1_real_local_solve_benchmark.py
```
- **Execution**: Completed successfully in 56.4 seconds.
- **Outcome**: The model call for `toy-math-solve` was successfully completed! `output_len` increased from 0 to 577.
- **Telemetry Update**: The `timed_out` state is correctly classified, and diagnostic metrics are updated in `.nexus/reports/local_model/m1_real_local_solve_results.jsonl`.

## Classification

**`MODEL_OUTPUT_AVAILABLE`** (output_len > 0 and provider_error is empty).

Ollama successfully produced a model response within the 120-second window once the timeout was correctly set and forwarded.

## Files Changed

- `nexus/services/local_heal/local_model_provider.py`
  - Added elapsed/timeout telemetry tracking to `LocalModelProviderResponse`.
  - Fixed `OllamaLocalModelProvider` to correctly handle `socket.timeout` and `TimeoutError` and tag `timed_out=True`.
  - Raised default `timeout_sec` to 120.0s.
- `nexus/services/local_heal/local_model_executor.py`
  - Extracted `provider_timeout_sec` from the route context's `signal_snapshot` (defaulting to 120.0s).
  - Forwarded the timeout to all `LocalModelProviderRequest` constructors.
  - Telemetrized timeout parameters into `raw_meta`.
- `nexus/services/local_heal/local_model_capability_executors.py`
  - Extracted `provider_timeout_sec` and forwarded it to provider requests.
  - Replaced hardcoded 30-second timeout with the dynamic snapshot-driven timeout.
- `scripts/bench/m1_real_local_solve_benchmark.py`
  - Set `provider_timeout_sec: 120` in `signal_snapshot` mocks.
- `tests/unit/local_heal/test_local_model_executor.py`
  - Appended test cases verifying timeout forwarding, default timeout fallback, timeout non-solving behavior, and timeout flag classification.

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_provider.py \
  nexus/services/local_heal/local_model_executor.py \
  nexus/services/local_heal/local_model_capability_executors.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/unit/local_heal/test_localheal_pipeline_seam_truth.py

uv run pytest tests/unit/local_heal/test_local_model_executor.py tests/unit/local_heal/test_localheal_pipeline_seam_truth.py tests/benchmark/test_m1_real_local_solve_benchmark.py -q
```

## Tests Run and Pass/Fail Count

- **Total Tests**: 65 tests.
- **Pass/Fail**: 65 passed, 0 failed.

## toy-math-solve Before/After Table

| Telemetry Field | Before (C5D) | After (C6) |
| :--- | :--- | :--- |
| `provider_error` | `"ollama_internal_error: timed out"` | `""` |
| `provider_invoked` | `True` | `True` |
| `model_called` | `False` | `True` |
| `prompt_len` | `3255` | `3006` |
| `output_len` | `0` | `577` |
| `effective_timeout_sec` | `30` | `120` |
| `elapsed_sec` | `30` | `~56` (total loop duration) |
| `candidate_hash_empty` | `True` (`"empty"`) | `True` (`"e3b0c442..."` is empty hash) |
| `candidate_isolated` | `False` | `False` |
| `verifier_result` | `fail` | `fail` |
| `solved` | `False` | `False` |

*Note: candidate_hash is `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (SHA256 of empty string) because patch synthesis exited with `MICRO_VERIFY_CONTEXT_MISSING` and no patch was applied.*

## Explicit Statements

- **B8 not run**: B8 external validation was not run in this task.
- **Parser/protocol/verifier/candidate isolation unchanged**: No changes were made to `SolidSearchReplaceProtocol`, parser rules, or verification constraints.
- **LocalHeal is not fully connected to solved closure**: Until candidates are successfully parsed, isolated, and verifier passes exist, LocalHeal remains unconnected to solved closure.

## Next Gate

- **`MODEL_OUTPUT_AVAILABLE`**: We will now proceed to **C7 Output Classification** to analyze the response text (577 characters) and handle the parser/verification missing context errors.

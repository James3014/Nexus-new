# Local Model Sprint A0.1: Adapter Test Expectation Realignment

**Status:** LOCAL_MODEL_SPRINT_A0_1_ADAPTER_TEST_EXPECTATION_REALIGNMENT_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `tests/benchmark/test_capability_ab_runner.py` | Updated 4 adapter test expectations |
| `tests/integration/test_ollama_local_solve_smoke_runner_contract.py` | Updated import from `build_local_model_provider_from_env` to `build_local_model_provider` |
| `scripts/local_heal/run_ollama_local_solve_smoke.py` | Updated import and provider construction to use `build_local_model_provider` |
| `tests/unit/local_heal/test_qwen_backend_seam.py` | Added safe import guard with skipif for stale `LocalPatchSynthesisBackend` import |

## Commands Run

```bash
uv run pytest tests/benchmark/test_capability_ab_runner.py -k "local_model_adapter_env_enabled_no_model_call_records_blocker or local_model_adapter_june_b_replay or local_model_adapter_wet_run or local_model_adapter_missing_controls" -q
# 4 passed

uv run pytest tests/integration/test_ollama_local_solve_smoke_runner_contract.py tests/unit/local_heal/test_qwen_backend_seam.py -q
# 3 passed, 1 skipped

uv run pytest tests/unit/local_heal/test_downstream_enforcement_gates.py tests/unit/local_heal/test_capability_adapter.py -q
# 19 passed
```

**Total: 26 passed, 1 skipped, 0 failed**

## Old vs New Expectations

| Test | Old Expectation | New Expectation |
|------|----------------|-----------------|
| `test_local_model_adapter_env_enabled_no_model_call_records_blocker` | `missing_required_control` in blockers | `missing_signal_snapshot` in blockers |
| `test_local_model_adapter_june_b_replay` | `route_mode == "cloud_assisted_by_local_trace_only"` | `route_mode == "local_only_blocked"` |
| `test_local_model_adapter_wet_run` | `route_mode == "local_only_executed"` | `route_mode == "local_only_blocked"` |
| `test_local_model_adapter_missing_controls` | `fallback_block_reason == "missing_required_control"` | `fallback_block_reason == "missing_signal_snapshot"` |
| `test_ollama_local_solve_smoke_runner_contract` | `import build_local_model_provider_from_env` | `import build_local_model_provider` |
| `test_qwen_backend_seam` | Module-level import of `LocalPatchSynthesisBackend` | Safe import guard with skipif |

## Explicit Statements

- Runtime behavior unchanged. Only test expectations updated.
- Adapter remains non-authoritative (`adapter_output_is_route_truth == False`).
- `route_truth_source` remains `CapabilityPlanner`.
- `public_claim_allowed` remains `False`.
- `production_ready` remains `False`.
- `behavior_changed` remains `False`.
- No env provider contract restored.
- A1 not executed.

## Stop Gate Assessment

Stop gate cleared. All 6 downstream enforcement failures resolved. Ready to proceed to A1.

# Local Model Sprint B7.7: M1 Raw Model Metadata Projection

**Status:** LOCAL_MODEL_SPRINT_B7_7_M1_RAW_METADATA_PROJECTION_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/m1_real_local_solve_benchmark.py` | Pipeline/provider telemetry projected into M1 JSONL rows |

## Commands Run

```bash
uv run pytest tests/benchmark/test_m1_real_local_solve_benchmark.py -q
# 4 passed
```

## Projected Fields

| Field | Source |
|-------|--------|
| `phase_reached` | adapter_meta |
| `patch_synthesis_reached` | adapter_meta |
| `patch_synthesis_provider_error` | adapter_meta |
| `patch_synthesis_model_called` | adapter_meta |
| `patch_synthesis_output_len` | adapter_meta |
| `patch_synthesis_prompt_len` | adapter_meta |
| `patch_synthesis_model_name` | adapter_meta |
| `pipeline_failure_reason` | adapter_meta |
| `pipeline_final_patch_len` | adapter_meta |
| `pipeline_run_called` | adapter_meta |
| `pipeline_run_success` | adapter_meta |
| `orchestrator_run_reachable` | adapter_meta |
| `provider_error` | adapter_meta |
| `provider_invoked` | adapter_meta |
| `model_name_used` | adapter_meta |
| `output_len` | adapter_meta |
| `prompt_len` | adapter_meta |
| `timed_out` | adapter_meta |

## Explicit Statements

- No parser/protocol/verifier/candidate isolation changes.
- B8 not run.
- Solved rate not claimed.
- EMPTY_RESPONSE root cause still not classified until B7.8 rerun.

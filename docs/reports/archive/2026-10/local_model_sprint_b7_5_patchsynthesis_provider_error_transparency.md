# Local Model Sprint B7.5: PatchSynthesis Provider Error Transparency

**Status:** LOCAL_MODEL_SPRINT_B7_5_PATCHSYNTHESIS_PROVIDER_ERROR_TRANSPARENCY_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_capability_executors.py` | Provider diagnostics preserved in telemetry |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_localheal_pipeline_seam_truth.py tests/unit/local_heal/test_local_model_executor.py tests/unit/local_heal/test_downstream_enforcement_gates.py -q
# 64 passed
```

## Provider Error Taxonomy

| Error | Source | Behavior |
|-------|--------|----------|
| `provider_not_configured` | OllamaLocalModelProvider — env missing | Exposed in `provider_error` |
| `model_name_missing` | OllamaLocalModelProvider — model empty | Exposed in `provider_error` |
| `ollama_http_error_XXX` | OllamaLocalModelProvider — HTTP error | Exposed in `provider_error` |
| `ollama_url_error` | OllamaLocalModelProvider — connection error | Exposed in `provider_error` |
| `injected_provider_error` | InjectedLocalModelProvider — exception | Exposed in `provider_error` |
| `""` (empty) | Provider returned empty output | Exposed in `output_len=0` |

## Telemetry Fields Added

| Field | Description |
|-------|-------------|
| `phase_reached` | Last pipeline phase reached |
| `patch_synthesis_reached` | Whether patch synthesis was reached |
| `patch_synthesis_provider_error` | Provider error from patch synthesis |
| `patch_synthesis_model_called` | Whether model was called in patch synthesis |
| `patch_synthesis_output_len` | Output length from patch synthesis |
| `patch_synthesis_prompt_len` | Prompt length sent to model |
| `patch_synthesis_model_name` | Model name used in patch synthesis |
| `provider_error` | Provider error (same as patch_synthesis_provider_error) |
| `provider_invoked` | Whether provider was invoked |
| `model_called` | Whether model was called |
| `model_name_used` | Model name used |
| `timed_out` | Whether request timed out |
| `output_truncated` | Whether output was truncated |
| `output_len` | Output length |
| `prompt_len` | Prompt length |

## Explicit Statements

- No parser/protocol/verifier/candidate isolation changes.
- B8 not run.
- Solved rate not claimed.
- Provider errors are now observable, not collapsed into EMPTY_RESPONSE.

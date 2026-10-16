# Local Model Sprint B7.1: Provider Contract Smoke

**Status:** LOCAL_MODEL_SPRINT_B7_1_PROVIDER_CONTRACT_SMOKE_COMPLETE
**Date:** 2026-07-01

## Root Cause Found

**`_provider_generate` signature mismatch with `OllamaLLMClient`.**

`OllamaLLMClient.generate()` calls `self.generate_fn(system_prompt, user_prompt)` — two positional string arguments.

Bridge's `_provider_generate` only accepted one `req` argument → `TypeError` → caught as `MODEL_PROVIDER_ERROR`.

## Fix Applied

Updated `_provider_generate` to accept both signatures:
1. `(system_prompt, user_prompt, **kwargs)` — from OllamaLLMClient
2. `(req)` — from LocalModelProviderRequest

## Ollama Daemon Status

- **Reachable**: Yes (localhost:11434)
- **Available models**: qwen2.5-coder:7b-instruct, deepseek-coder:6.7b-instruct, qwen2.5-coder:14b-instruct-q3_K_M, etc.

## Provider Error Classification

| Error | Cause |
|-------|-------|
| `provider_not_configured` | `NEXUS_LOCAL_MODEL_CALL_ALLOWED` missing or `NEXUS_LOCAL_MODEL_PROVIDER` != "ollama" |
| `model_name_missing` | `request.model_name` and `NEXUS_LOCAL_MODEL_NAME` both empty |
| `ollama_http_error_XXX` | Ollama HTTP error |
| `ollama_url_error` | Ollama connection error |
| `MODEL_PROVIDER_ERROR` (before fix) | `_provider_generate` signature mismatch |

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_capability_executors.py` | Fixed `_provider_generate` signature |
| `nexus/services/local_heal/local_model_executor.py` | Fixed committee retry `_provider_generate` signature |
| `tests/unit/local_heal/test_localheal_pipeline_provider_contract.py` | Added 5 B7.1 tests |

## Explicit Statements

- No parser/protocol/verifier/candidate isolation changes.
- B8 not run.
- Solved rate not claimed.
- Provider daemon reachable — contract propagation was broken, now fixed.

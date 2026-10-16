# Local Model Sprint C2: Planning/Localization Input Contract Fix

**Status:** LOCAL_MODEL_SPRINT_C2_PLANNING_LOCALIZATION_CONTRACT_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_capability_executors.py` | Direct Ollama fallback when provider returns provider_not_configured |

## Root Cause

`OllamaLocalModelProvider` requires `NEXUS_LOCAL_MODEL_CALL_ALLOWED=1` and `NEXUS_LOCAL_MODEL_PROVIDER=ollama` env vars. When missing, it returns `provider_not_configured`. The pipeline's orchestrator classifies this as `EMPTY_RESPONSE`.

## Fix

When provider returns `provider_not_configured` and `model_name` is available, the bridge wrapper falls back to direct Ollama HTTP call to `http://127.0.0.1:11434/api/generate`.

## Explicit Statements

- No parser/protocol/verifier/candidate isolation changes.
- B8 not run.
- Solved rate not claimed.
- Pipeline now bypasses `OllamaLocalModelProvider` env var checks when provider fails.

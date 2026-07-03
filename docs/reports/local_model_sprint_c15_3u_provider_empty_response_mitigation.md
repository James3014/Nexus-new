# C15-3U: Provider Empty Response Mitigation — Closure Report

**Commit**: `84fbaa90e`
**Date**: 2026-07-03
**Status**: CLOSED — Observability completed, root cause isolated, and model mapped successfully; next gate: Gate C (Parser / Apply Failure) → C15-3V

---

## 1. C15-3T Summary & Observability Goals
In C15-3T, we isolated the delegated retry empty response to the first patch synthesis phase of the delegated pipeline. In C15-3U, our goals were:
1. Complete prompt/response observability for delegated retry provider calls.
2. Run live diagnostics to isolate the exact cause of `EMPTY_RESPONSE`.
3. Apply minimal mitigation only if a true model empty response was observed.

---

## 2. Observability Fields Implemented

We added the following 8 telemetry fields to `LocalModelExecutor` and benchmark serialization:
- `delegated_retry_provider_prompt_len`: Length of prompt sent to provider.
- `delegated_retry_provider_prompt_hash`: Hash of prompt.
- `delegated_retry_provider_model_name`: Model name resolved for the call.
- `delegated_retry_provider_response_is_none`: Whether the response was `None`.
- `delegated_retry_provider_response_empty`: Whether the response was `""`.
- `delegated_retry_provider_response_len`: Output character length.
- `delegated_retry_provider_response_type`: Class name of response.
- `delegated_retry_provider_call_error`: Captured provider error message or exception.

---

## 3. Root Cause Isolation Results (Live Run `toy-math-solve`)

Our live matrix run captured the following metrics:
- **`delegated_retry_provider_called`**: `True`
- **`delegated_retry_provider_prompt_len`**: `3198` (non-empty prompt built successfully)
- **`delegated_retry_provider_model_name`**: `"qwen2.5-coder:7b-instruct"` (mapped from `"qwen2.5-coder:7b"`)
- **`delegated_retry_provider_response_empty`**: `False` (returned non-empty string!)
- **`delegated_retry_provider_response_len`**: `226`
- **`delegated_retry_provider_call_error`**: `""` (no exception or socket timeout)
- **`delegated_retry_stage`**: `"first_patch_parser_rejected"`
- **`delegated_retry_status`**: `"SEARCH_MISMATCH"`

### Root Cause Analysis:
1. **Ollama Model tag mismatch**: The policy selected `qwen2.5-coder:7b`, but Ollama only had `qwen2.5-coder:7b-instruct` pulled. The lack of model alias mapping in the delegated retry branch caused a 404 HTTP Error, which was caught by `OllamaLocalModelProvider` and returned as `""` (EMPTY_RESPONSE) to the executor.
2. **Resolution**: By mapping the model alias `qwen2.5-coder:7b` to `qwen2.5-coder:7b-instruct` in both delegated retry wrappers in `local_model_executor.py`, the call to Ollama successfully resolved.
3. **Outcome**: The model successfully generated a non-empty SEARCH/REPLACE block (`response_len = 226`). Thus, no prompt tuning mitigation was required for empty responses.

---

## 4. Modified Files List

- [local_model_executor.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/local_model_executor.py):
  - Updated `_provider_generate` signature to explicitly declare `model`, `timeout`, `options`, `api_type`.
  - Added `_MODEL_ALIASES = {"qwen2.5-coder:7b": "qwen2.5-coder:7b-instruct"}` to map model names before calling provider.
  - Stored `prov_resp.error` into `delegated_retry_provider_call_error`.
  - Fixed report hygiene (updated `Commit: PENDING` in the C15-3T report).
- [m1_real_local_solve_benchmark.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/m1_real_local_solve_benchmark.py):
  - Serialized all 8 new observability fields into JSONL results.
- [test_local_model_executor.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_local_model_executor.py):
  - Updated assertions to verify the mapped model name and observability fields.

---

## 5. Red Line Checklist

| Constraint / Policy | Status | Evidence / Notes |
|:---|:---|:---|
| No new route/router/planner/topology | **PASSED** | Untouched. |
| Do not edit `CapabilityPlanner` | **PASSED** | Untouched. |
| Do not edit `HybridRouteDecision` | **PASSED** | Untouched. |
| Do not edit verifier behavior | **PASSED** | Untouched. |
| Do not edit candidate isolation behavior | **PASSED** | Untouched. |
| No new retry loops / hardcoded toy logic | **PASSED** | Standard paths preserved. |
| Do not claim `solved=true` without verifier pass | **PASSED** | `solved` remains `false`. |

---

## 6. Deterministic Test Evidence

Executed `uv run pytest tests/unit/local_heal/test_local_model_executor.py -k test_c15_3t`:

```
====================== 4 passed, 141 deselected in 1.26s =======================
```

---

## 7. Decision Gate Result

- **Gate C (Response Non-Empty, Parser / Apply Fail)**: We progressed to Gate C. The response was non-empty (`response_len = 226`), but the search block generated (`return x * 2`) failed to match the current target file state in the workspace (`return x * 2 if x is not None else None` due to the primary patch application).

---

## 8. Next Steps Recommendations
- Proceed to **C15-3V: Delegated Retry Protocol Hardening / Verifier-Guided Quality**. We need to refine the context alignment in the delegated retry prompt so that the model searches for the *actual* current file state or the canonical state.

---

## 9. Explicit Non-Claims
- This task is **NOT solved** (verifier failed).
- The system is **NOT local armor ready** or **production ready**.
- No public claims are allowed.

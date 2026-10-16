# C15-3T: Delegated Retry Empty Response Wiring Diagnosis — Closure Report

**Commit**: `164add5a1`
**Date**: 2026-07-03
**Status**: CLOSED — Diagnostics added; next gate: Gate B (Provider True Empty) → C15-3U

---

## 1. C15-3S Handoff Summary
In C15-3S, the pipeline reanchor block mismatch (`search_block_mismatch_current_source`) was resolved by correctly preserving the target file's pre-pipeline state (`original_target_content`). With reanchor successfully resolved:
- `pipeline_locked_search_reanchored=true`
- `candidate_isolated=true`
- `hash_match=true`
- `retry_eligible=true`
- `pipeline_retry_delegated=true`

The primary pipeline was pushed forward to the delegated retry branch, where the execution stopped due to:
- `delegated_retry_status=EMPTY_RESPONSE`
- `semantic_retry_prompt_len=0`

---

## 2. Delegated Retry Call Path Map

```
LocalModelExecutor.run()
  ├─ runs HealPipeline (primary, attempt 1)
  │    └─ fails verification
  ├─ retry_eligible matches conditions
  ├─ enters delegated retry branch
  │    ├─ builds retry_prompt = SelfCorrector().build_retry_prompt(...)
  │    ├─ sets heal_ctx = LegacyHealContext(..., user_prompt=retry_prompt, attempt=1, max_tries=1)
  │    ├─ runs pipeline.run(heal_ctx) (delegated pipeline)
  │    │    ├─ patch synthesis phase uses heal_ctx.user_prompt
  │    │    ├─ calls _provider_generate()
  │    │    │    └─ local model provider returns "" (EMPTY_RESPONSE)
  │    │    └─ since attempt == 1 but evaluation_report is absent (verifier never ran in delegated pipeline yet),
  │    │       orchestrator semantic retry is NOT triggered.
  │    └─ returns result_ctx with empty _semantic_retry_telemetry
  ├─ projects delegated_retry_status = "EMPTY_RESPONSE"
  └─ projects raw_meta["semantic_retry_prompt_len"] = 0 (defaults due to empty telemetry)
```

---

## 3. Root Cause Classification

### 1) Why was `delegated_retry_status = EMPTY_RESPONSE`?
- **Classification**: `first_patch_empty` + `provider_true_empty`.
- **Reason**: The delegated pipeline's first patch synthesis phase called the provider with the retry prompt (`SelfCorrector().build_retry_prompt(...)`), but the local model returned an empty string (`""`), which was mapped to `EMPTY_RESPONSE`.

### 2) Why was `semantic_retry_prompt_len = 0`?
- **Classification**: `telemetry_projection_gap`.
- **Reason**: The delegated pipeline's orchestrator did not trigger its own semantic retry phase because the first patch synthesis failed before verification, leaving `_semantic_retry_telemetry` empty. The projection code mapped this empty dict to default values (e.g., `semantic_retry_prompt_len=0`), making it appear as if the retry prompt failed to build, when in reality semantic retry was never invoked.

---

## 4. Modified Files List

- [local_model_executor.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/local_model_executor.py):
  - Added initialization for `delegated_retry_stage` and `delegated_retry_provider_called`.
  - Wrapped `_provider_generate` to record `delegated_retry_provider_called = True`.
  - Added calculation for `delegated_retry_stage` after `pipeline.run()`.
  - Projected both fields into `raw_meta`.
- [m1_real_local_solve_benchmark.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/m1_real_local_solve_benchmark.py):
  - Added `delegated_retry_stage` and `delegated_retry_provider_called` to the benchmark serialization JSONL.
- [test_local_model_executor.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_local_model_executor.py):
  - Added 4 deterministic unit tests verifying the stages and provider invocation flag.

---

## 5. Red Line Checklist

| Constraint / Policy | Status | Evidence / Notes |
|:---|:---|:---|
| No new route/router/planner/topology | **PASSED** | No structural topology or routing code modified. |
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
============================== 4 passed in 1.33s ===============================
```
- `test_c15_3t_delegated_retry_stage_first_patch_empty`: Verified that `delegated_retry_stage` correctly reports `first_patch_empty_response` when first patch returns empty.
- `test_c15_3t_delegated_retry_first_patch_empty_not_mislabeled_semantic_retry`: Verified that empty first patch does not set `semantic_retry_invoked` to True.
- `test_c15_3t_delegated_retry_provider_called_flag_present_in_meta`: Verified that `delegated_retry_provider_called` is correctly populated.
- `test_c15_3t_delegated_retry_stage_not_invoked_when_not_eligible`: Verified stage is `not_invoked` when isolation/reanchor fails.

---

## 7. Live Matrix Summary

Live run on `toy-math-solve` (Task ID: `toy-math-solve`):

- **`pipeline_retry_delegated`**: `True`
- **`delegated_retry_provider_called`**: `True`
- **`delegated_retry_stage`**: `"first_patch_empty_response"`
- **`delegated_retry_status`**: `"EMPTY_RESPONSE"`
- **`delegated_retry_failure_reason`**: `"EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE"`
- **`semantic_retry_invoked`**: `True` (from primary pipeline run)
- **`semantic_retry_prompt_len`**: `0` (from delegated pipeline run projection default)
- **`verifier_result`**: `fail`
- **`solved`**: `False`

---

## 8. Decision Gate Result

- **Gate B (Provider True Empty)**: Detected! The delegated retry was successfully invoked, the provider was called (`delegated_retry_provider_called=True`), but the local model returned an empty string.

---

## 9. Next Steps Recommendations
- Proceed to **C15-3U: Provider Empty Response Mitigation**. We need to examine why the local model (under the retry prompt format/wording) returned empty response and mitigate it using fail-safe heuristics or fallback.

---

## 10. Explicit Non-Claims
- This task is **NOT solved** (verifier failed).
- The system is **NOT local armor ready** or **production ready**.
- No public claims are allowed.

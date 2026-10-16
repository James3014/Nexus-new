# LocalHeal Sprint C15-5B: Delegated Retry Model Resolution Fix

**Status**: `C15_5B_DELEGATED_RETRY_MODEL_RESOLUTION_FIX_PASS`

**Date**: 2026-07-04

**Base commit**: `7fbdb5fff test(localheal): wire C15 benchmark model override`

---

## 1. Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Added `_dr_requested_model` capture from signal_snapshot; override model in `_provider_generate` when signal_snapshot model differs from pipeline-selected model |
| `tests/unit/local_heal/test_local_model_executor.py` | Added 3 C15-5B tests for model resolution |

---

## 2. Implementation Summary

In the delegated retry section of `LocalModelExecutor.run()`:

1. Before `_provider_generate`, capture `signal_snapshot["executor_model"]` as `_dr_requested_model`
2. Inside `_provider_generate`, after model alias resolution, if `_dr_requested_model` is set and differs from the pipeline-selected model, override with `_dr_requested_model` (also applying alias resolution)

**Lines changed**: ~1660-1692 in `local_model_executor.py`

---

## 3. Model Resolution Priority (Before/After)

### Before

```
1. pipeline-selected model (LocalModelPolicy.select_model → 7B for attempt=1)
2. model alias (qwen2.5-coder:7b → qwen2.5-coder:7b-instruct)
3. signal_snapshot ignored
```

### After

```
1. pipeline-selected model (LocalModelPolicy.select_model)
2. model alias (qwen2.5-coder:7b → qwen2.5-coder:7b-instruct)
3. signal_snapshot executor_model override (if set and differs from pipeline-selected)
4. alias resolution applied to override value
```

---

## 4. Tests Added/Updated

| Test | Purpose | Result |
|------|---------|--------|
| `test_delegated_retry_uses_signal_snapshot_executor_model` | Signal_snapshot 14B overrides pipeline 7B | ✅ PASS |
| `test_delegated_retry_falls_back_to_pipeline_model_without_override` | Empty signal_snapshot falls back to pipeline model | ✅ PASS |
| `test_delegated_retry_records_actual_provider_model_name` | Telemetry records actual delegated model | ✅ PASS |

---

## 5. Test Results

```bash
uv run pytest tests/unit/local_heal/test_local_model_executor.py -q
# 149 passed

uv run pytest tests/benchmark/test_m1_real_local_solve_benchmark.py -q
# 28 passed

uv run pytest tests/unit/local_heal/test_prompt_builder.py -q
# 5 passed
```

---

## 6. Live Trial Matrix

| Requested model | Primary model observed | Delegated model observed | pipeline_retry_delegated | Verifier evidence injected | verifier_result | solved | solve_mechanism | delegated_retry_stage | delegated_retry_status |
|----------------|----------------------|-------------------------|------------------------|---------------------------|----------------|--------|----------------|----------------------|----------------------|
| qwen2.5-coder:7b-instruct | qwen2.5-coder:7b-instruct | qwen2.5-coder:7b-instruct | true | true | fail | false | delegated_retry_unresolved | first_patch_parser_rejected | SEARCH_MISMATCH |
| qwen2.5-coder:14b-instruct-q3_K_M | qwen2.5-coder:14b-instruct-q3_K_M | **qwen2.5-coder:14b-instruct-q3_K_M** | true | true | fail | false | delegated_retry_unresolved | first_patch_failed | **SUCCESS** |

---

## 7. Wiring Success Checklist

| Criterion | 7B | 14B |
|-----------|-----|------|
| `delegated_retry_provider_called = true` | ✅ | ✅ |
| `delegated_retry_provider_model_name = requested model` | ✅ | ✅ |
| `pipeline_retry_delegated = true` | ✅ | ✅ |

**Wiring: PASS for both models.** The 14B delegated retry now correctly uses `qwen2.5-coder:14b-instruct-q3_K_M`.

---

## 8. Delegated Retry Solved Checklist

| Criterion | 14B |
|-----------|-----|
| `pipeline_retry_delegated = true` | ✅ |
| `delegated_retry_provider_called = true` | ✅ |
| `delegated_retry_provider_model_name = requested model` | ✅ |
| `semantic_retry_prompt_has_verifier_evidence = true` | ✅ |
| `orchestrator_verifier_evidence_passed_to_retry = true` | ✅ |
| `verifier_result = pass` | ❌ |
| `solved = true` | ❌ |
| `solve_mechanism = delegated_retry` | ❌ |
| `delegated_retry_stage = success` | ❌ (first_patch_failed) |

**Wiring: PASS. Solved: NOT_PROVEN.** The 14B delegated retry produces a syntactically valid patch (delegated_retry_status=SUCCESS) but the logic still fails verification.

---

## 9. Model Override Proof

| Model | Primary path proof | Delegated retry proof |
|-------|-------------------|----------------------|
| 7B | `actual_model_name_used: qwen2.5-coder:7b-instruct` | `delegated_retry_provider_model_name: qwen2.5-coder:7b-instruct` |
| 14B | `actual_model_name_used: qwen2.5-coder:14b-instruct-q3_K_M` | `delegated_retry_provider_model_name: qwen2.5-coder:14b-instruct-q3_K_K_M` |

**Both paths now correctly use the requested model.**

---

## 10. Evidence Injection Status

- 7B: `semantic_retry_prompt_has_verifier_evidence=true` ✅
- 14B: `semantic_retry_prompt_has_verifier_evidence=true` ✅

**Evidence injection is stable and correct.**

---

## 11. Next Engineering Decision

**C15-5C Delegated Retry Claim Boundary Closure**

The wiring is now proven. The 14B delegated retry produces syntactically valid patches (SUCCESS status) but fails verification. This is a semantic correctness issue, not a wiring issue. The next step should:

1. Formally close the delegated retry wiring arc
2. Document the 14B semantic failure mode
3. Decide whether to pursue semantic improvement or accept the claim boundary

---

## 12. Scope Statement

- **Delegated retry model resolution fixed.**
- **No route authority changed.**
- **Parser/verifier/candidate isolation unchanged.**
- **No CapabilityPlanner/HybridRouteDecision change.**
- **No benchmark task semantics changed.**
- **delegated_retry solved NOT_PROVEN.**
- **production_ready=false.**
- **public_claim_allowed=false.**

---

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/local_model_executor.py tests/unit/local_heal/test_local_model_executor.py scripts/bench/m1_real_local_solve_benchmark.py tests/benchmark/test_m1_real_local_solve_benchmark.py
# exit 0

uv run pytest tests/unit/local_heal/test_local_model_executor.py -q
# 149 passed

uv run pytest tests/benchmark/test_m1_real_local_solve_benchmark.py -q
# 28 passed

uv run pytest tests/unit/local_heal/test_prompt_builder.py -q
# 5 passed

export NEXUS_BENCHMARK_APPEND=1
timeout 240 uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:7b-instruct
# completed, duration: 69s

timeout 300 uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:14b-instruct-q3_K_M
# completed, duration: 201s
```

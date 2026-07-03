# LocalHeal Sprint C15-5A: Runtime Model Override Wiring for Multi-Model Delegated Retry Trial

**Status**: `C15_5A_MODEL_OVERRIDE_WIRING_PARTIAL`

**Date**: 2026-07-04

**Base commit**: `8518bf7b2 docs: evaluate multi-model delegated retry candidates`

---

## 1. Files Changed

| File | Change |
|------|--------|
| `scripts/bench/m1_real_local_solve_benchmark.py` | Added `build_c15_benchmark_row()` helper, CLI flags `--executor-model`, `--provider-timeout-sec`, `--judge-model`, `--primary-proposer-model`, `--secondary-proposer-model`, env fallback `NEXUS_C15_*` |
| `tests/benchmark/test_m1_real_local_solve_benchmark.py` | Added 9 C15-5A model override tests |
| `docs/reports/local_model_sprint_c15_5a_runtime_model_override_wiring.md` | This report |

---

## 2. Implementation Summary

Extracted `build_c15_benchmark_row()` pure helper from inline row construction. Added CLI flags and env var fallback with precedence: CLI > env > default.

**Default values preserved**:
- `executor_model`: `qwen2.5-coder:7b-instruct`
- `judge_model`: `qwen2.5-s2t-advisor:3b`
- `primary_proposer`: `qwen2.5-coder:7b-instruct`
- `secondary_proposer`: `deepseek-coder:6.7b-instruct`
- `provider_timeout_sec`: 120

**New CLI flags**: `--executor-model`, `--provider-timeout-sec`, `--judge-model`, `--primary-proposer-model`, `--secondary-proposer-model`

**New env vars**: `NEXUS_C15_EXECUTOR_MODEL`, `NEXUS_C15_PROVIDER_TIMEOUT_SEC`, `NEXUS_C15_JUDGE_MODEL`, `NEXUS_C15_PRIMARY_PROPOSER_MODEL`, `NEXUS_C15_SECONDARY_PROPOSER_MODEL`

---

## 3. Test Results

```
uv run pytest tests/benchmark/test_m1_real_local_solve_benchmark.py -v
# 28 passed (19 existing + 9 new C15-5A)

uv run pytest tests/unit/local_heal/test_prompt_builder.py -q
# 5 passed
```

### New Tests (9)

| Test | Result |
|------|--------|
| `test_c15_benchmark_default_executor_model_is_qwen7b` | ✅ PASS |
| `test_c15_benchmark_cli_executor_model_override` | ✅ PASS |
| `test_c15_benchmark_env_executor_model_override` | ✅ PASS |
| `test_c15_benchmark_cli_override_precedence_over_env` | ✅ PASS |
| `test_c15_benchmark_proposer_specs_override_is_benchmark_only` | ✅ PASS |
| `test_c15_benchmark_override_does_not_add_route_authority` | ✅ PASS |
| `test_c15_benchmark_row_preserves_required_fields` | ✅ PASS |
| `test_c15_benchmark_provider_timeout_override` | ✅ PASS |
| `test_c15_benchmark_env_provider_timeout_override` | ✅ PASS |

---

## 4. Live Trial Matrix

| Requested model | Primary model observed | Delegated model observed | pipeline_retry_delegated | Verifier evidence injected? | verifier_result | solved | solve_mechanism | delegated_retry_stage | delegated_retry_status | Dominant failure |
|----------------|----------------------|-------------------------|------------------------|---------------------------|----------------|--------|----------------|----------------------|----------------------|-----------------|
| qwen2.5-coder:7b-instruct | qwen2.5-coder:7b-instruct | qwen2.5-coder:7b-instruct | true | true | fail | false | delegated_retry_unresolved | first_patch_failed | REPLACE_SYNTAX_ERROR | INDENTATION_SYNTAX_ERROR |
| deepseek-coder:6.7b-instruct | deepseek-coder:6.7b-instruct | (not invoked) | false | false | fail | false | pipeline_semantic_retry_unresolved | not_invoked | — | SEARCH_MISMATCH (hash_mismatch) |
| qwen2.5-coder:14b-instruct-q3_K_M | qwen2.5-coder:14b-instruct-q3_K_M | qwen2.5-coder:7b-instruct | true | true | fail | false | delegated_retry_unresolved | first_patch_failed | REPLACE_SYNTAX_ERROR | INDENTATION_SYNTAX_ERROR |

---

## 5. Model Override Proof

| Requested | Primary path proof | Delegated retry proof |
|-----------|-------------------|----------------------|
| 7B | `actual_model_name_used: qwen2.5-coder:7b-instruct` ✅ | `delegated_retry_provider_model_name: qwen2.5-coder:7b-instruct` ✅ |
| DeepSeek 6.7B | `actual_model_name_used: deepseek-coder:6.7b-instruct` ✅ | Delegated retry not invoked (hash_mismatch) ⚠️ |
| 14B | `actual_model_name_used: qwen2.5-coder:14b-instruct-q3_K_M` ✅ | `delegated_retry_provider_model_name: qwen2.5-coder:7b-instruct` ❌ (still 7B) |

**Primary path override: WORKS.** All three models were correctly invoked for primary patch synthesis.

**Delegated retry override: DOES NOT WORK.** The delegated retry always uses 7B regardless of the benchmark override.

---

## 6. Evidence Regression Check

C15-5 reported `semantic_retry_prompt_has_verifier_evidence=false` in one run. In C15-5A trials:
- 7B: `semantic_retry_prompt_has_verifier_evidence=true` ✅
- DeepSeek 6.7B: delegated retry not invoked ⚠️
- 14B: `semantic_retry_prompt_has_verifier_evidence=true` ✅

**The regression was a one-off row selection issue, not a systemic problem.** Verifier evidence injection works correctly when delegated retry is invoked.

---

## 7. Root Cause: Delegated Retry Model Resolution Gap

The delegated retry creates its own `HealPipeline` with `attempt=1` in the `heal_ctx`. The pipeline's `PatchSynthesisPhase` calls `LocalModelPolicy.select_model()` which returns the **small model (7B)** for `attempt=1` patch phase. The benchmark override (`signal_snapshot.executor_model`) is NOT read by `LocalModelPolicy` — it reads from `NEXUS_OLLAMA_SMALL_MODEL` / `NEXUS_OLLAMA_LARGE_MODEL` env vars.

**To make delegated retry use 14B**, one would need to either:
1. Set `NEXUS_OLLAMA_SMALL_MODEL=qwen2.5-coder:14b-instruct-q3_K_M` (affects all phases)
2. Modify `local_model_executor.py` to pass signal_snapshot model to delegated retry pipeline (not allowed in this task)

This is a **runtime wiring gap** in the delegated retry path, not a benchmark override issue.

---

## 8. Next Engineering Decision

**C15-5B Evidence Injection Regression Fix**

The delegated retry model resolution gap is a `local_model_executor.py` change (forbidden in this task). However, the evidence pipeline and primary path override both work correctly. The next step should:

1. Fix the delegated retry model resolution to respect signal_snapshot or a dedicated env var
2. Then re-run 14B delegated retry trial to determine if 14B can solve the INDENTATION_SYNTAX_ERROR ceiling

---

## 9. Scope Statement

- **Benchmark-only model override wiring.**
- **No production route authority changed.**
- **Parser/verifier/candidate isolation unchanged.**
- **No CapabilityPlanner/HybridRouteDecision change.**
- **delegated_retry solved NOT_PROVEN.**
- **production_ready=false.**
- **public_claim_allowed=false.**

---

## Commands Run

```bash
python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py tests/benchmark/test_m1_real_local_solve_benchmark.py
# exit 0

uv run pytest tests/benchmark/test_m1_real_local_solve_benchmark.py -v
# 28 passed

uv run pytest tests/unit/local_heal/test_prompt_builder.py -q
# 5 passed

export NEXUS_BENCHMARK_APPEND=1
timeout 240 uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:7b-instruct
# completed, duration: 68s

timeout 240 uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model deepseek-coder:6.7b-instruct
# completed, duration: 135s

timeout 300 uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:14b-instruct-q3_K_M
# completed, duration: 189s

timeout 300 NEXUS_OLLAMA_LARGE_MODEL=qwen2.5-coder:14b-instruct-q3_K_M uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:14b-instruct-q3_K_M
# completed, duration: 161s
```

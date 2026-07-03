# LocalHeal Sprint C15-5: Multi-Model Committee and New Model Trial for Delegated Retry

**Status**: `C15_5_MULTI_MODEL_TRIAL_RUNTIME_WIRING_GAP`

**Date**: 2026-07-04

**Base commit**: `bbced6b78 docs: define delegated retry claim boundary`

---

## 1. Installed Model Inventory

```
NAME                                 ID              SIZE      MODIFIED
qwen2.5-coder:7b-instruct            3c6217f476a7    4.7 GB    4 days ago
deepseek-coder:6.7b-instruct         ce298d984115    3.8 GB    4 days ago
qwen2.5-coder:14b-instruct-q3_K_M    e00d09afd55a    7.3 GB    12 days ago
deepseek-r1-14b-q4km:latest          2499dfb9e4e2    9.0 GB    2 weeks ago
gemma4-coder-12b-q4km:latest         c0d776a20fb6    7.4 GB    2 weeks ago
qwen2.5:1.5b                         65ec06548149    986 MB    2 weeks ago
qwen2.5-s2t-advisor:3b               357c53fb659c    1.9 GB    2 weeks ago
nomic-embed-text:latest              0a109f422b47    274 MB    4 weeks ago
```

**Free disk space**: 92 GB

---

## 2. Download Attempts

| Candidate | Source | Size | Status | Reason |
|-----------|--------|------|--------|--------|
| Ornith-1.0-9B-GGUF | ollama.com/library/ornith:9b | 5.6 GB | **DOWNLOAD_FAILED** | Requires Ollama > 0.30.7 (current: 0.30.7) |
| Qwythos-9B | ollama.com | N/A | **NOT_AVAILABLE** | 404 on Ollama library |

---

## 3. Runtime Wiring Gap — Critical Finding

**The benchmark script (`m1_real_local_solve_benchmark.py:414`) hardcodes `executor_model: "qwen2.5-coder:7b-instruct"` in the `signal_snapshot`.** The local model executor reads the model from `signal_snapshot["executor_model"]` (local_model_executor.py:440), not from environment variables.

This means:
- **Cannot switch executor model** without modifying the benchmark script
- **Cannot change proposer_specs** without modifying the benchmark script
- **Cannot test 14B, DeepSeek, gemma, or any other model** through the standard benchmark path
- **Cannot test heterogeneous committee combinations** through the standard benchmark path

Environment variable `NEXUS_OLLAMA_MODEL` exists in `capability_ab_runner.py` but is NOT read by the benchmark's signal_snapshot construction.

**This is the primary blocker for multi-model trials.**

---

## 4. Trial Matrix

| Group | Model/Combination | Available? | Attempts | Best verifier_result | Best solved | Best solve_mechanism | Best delegated_retry_stage | Dominant failure | Telemetry complete? | Decision |
|-------|------------------|-----------|----------|---------------------|-------------|---------------------|--------------------------|-----------------|--------------------|----------| 
| A1 | qwen2.5-coder:7b-instruct | ✅ | 5 (cumulative) | fail | false | delegated_retry_unresolved | first_patch_failed | INDENTATION_SYNTAX_ERROR (3/5), SYNTAX_ERROR (1/5), SEARCH_NOT_EXACT_SOURCE (1/5) | ✅ | BASELINE_CONFIRMED |
| A2 | deepseek-coder:6.7b-instruct | ✅ installed | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| A3 | qwen2.5-coder:14b-instruct-q3_K_M | ✅ installed | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| A4 | gemma4-coder-12b-q4km:latest | ✅ installed | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| A5 | deepseek-r1-14b-q4km:latest | ✅ installed | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| B1 | Qwen 7B primary + DeepSeek 6.7B secondary | signal_snapshot hardcoded | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| B2 | DeepSeek 6.7B primary + Qwen 7B secondary | signal_snapshot hardcoded | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| B3 | 3B advisor + Qwen 7B + DeepSeek 6.7B | signal_snapshot hardcoded | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| B4 | Qwen 7B + DeepSeek 6.7B + 14B fallback | signal_snapshot hardcoded | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| B5 | Qwen 7B + 14B fallback | signal_snapshot hardcoded | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| C1 | local_committee_only | signal_snapshot hardcoded | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| C2 | NEXUS_USE_COMMITTEE path | signal_snapshot hardcoded | 0 | — | — | — | — | — | — | NOT_RUN_RUNTIME_WIRING_MISSING |
| D1 | Ornith-1.0-9B-GGUF | ❌ download failed | 0 | — | — | — | — | — | — | DOWNLOAD_FAILED |
| D2 | Qwythos-9B | ❌ not available | 0 | — | — | — | — | — | — | NOT_AVAILABLE |
| D3 | Ornith + committee | ❌ model not installed | 0 | — | — | — | — | — | — | BLOCKED_BY_D1 |
| D4 | Qwythos + committee | ❌ model not available | 0 | — | — | — | — | — | — | BLOCKED_BY_D2 |

---

## 5. Latest Baseline Run (C15-5)

| Field | Value |
|-------|-------|
| `task_id` | toy-math-verifier-evidence-gap |
| `pipeline_retry_delegated` | true |
| `delegated_retry_provider_called` | true |
| `delegated_retry_status` | SYNTAX_ERROR |
| `delegated_retry_stage` | first_patch_failed |
| `semantic_retry_prompt_has_verifier_evidence` | **false** (regression from C15-4D-3) |
| `orchestrator_verifier_evidence_passed_to_retry` | **false** (regression) |
| `verifier_result` | fail |
| `solved` | false |
| `solve_mechanism` | delegated_retry_unresolved |
| `pipeline_failure_reason` | LOGIC_REGRESSION:VERIFICATION_FAILED |

**Observation**: This run shows `semantic_retry_prompt_has_verifier_evidence=false`, which is a regression from C15-4D-3 where it was `true`. The delegated retry still failed with SYNTAX_ERROR. The verifier evidence injection appears inconsistent across runs.

---

## 6. Success Criteria Checklist

| Criterion | Status |
|-----------|--------|
| `task_id = toy-math-verifier-evidence-gap` | ✅ |
| `pipeline_retry_delegated = true` | ✅ |
| `delegated_retry_provider_called = true` | ✅ |
| `semantic_retry_prompt_has_verifier_evidence = true` | ❌ (false in latest run) |
| `orchestrator_verifier_evidence_passed_to_retry = true` | ❌ (false in latest run) |
| `verifier_result = pass` | ❌ |
| `solved = true` | ❌ |
| `solve_mechanism = delegated_retry` | ❌ |
| `delegated_retry_stage = success` | ❌ |

**0/9 success criteria met in latest run. delegated_retry solved remains NOT_PROVEN.**

---

## 7. Committee Assessment

| Type | Status | Evidence |
|------|--------|----------|
| True heterogeneous dual proposer | **NOT_RUN** | signal_snapshot hardcodes proposer_specs |
| Same-model multi-sample committee | **NOT_RUN** | benchmark does not support this topology |
| 3B judge/advisor | **AVAILABLE** (qwen2.5-s2t-advisor:3b) | installed, used as judge_model in signal_snapshot |
| 14B fallback | **AVAILABLE** (qwen2.5-coder:14b-instruct-q3_K_M) | installed, but not wired to delegated retry |
| Runtime wiring missing | **CONFIRMED** | benchmark hardcodes executor_model and proposer_specs |

---

## 8. Historical June Evidence Alignment

The historical June benchmark reports showed:
- Single Qwen 7B route was weak
- Heterogeneous Qwen 7B + DeepSeek 6.7B / 3B judge + dual proposer route produced much better results

**Current result CONTRADICTS the historical claim** that heterogeneous routing improves results, because:
1. The heterogeneous route cannot be tested — benchmark hardcodes the model
2. The signal_snapshot shows `proposer_specs` with both Qwen 7B and DeepSeek 6.7B, but the local model executor only uses `executor_model` (Qwen 7B)
3. The historical route audit correctly identified that the historical route is NOT fully reattached to runtime

**This confirms C15-4E's finding**: the infrastructure is proven but the multi-model routing is not wired to the delegated retry path.

---

## 9. Next Engineering Decision

**Selected: C15-5A Reattach Heterogeneous Dual Proposer to Delegated Retry**

**Rationale:**
- The benchmark hardcodes `executor_model` in signal_snapshot — this is the root cause of the RUNTIME_WIRING_GAP
- The local model executor reads from `signal_snapshot["executor_model"]` (line 440) — this is the single-model bottleneck
- Historical evidence shows heterogeneous routing works better — but it's not wired to delegated retry
- The fix is to make the benchmark/executor support model override via signal_snapshot or env var
- This is a bounded, safe change that enables all Group A/B/C trials

**Rejected paths:**
- **Add Targeted 14B Fallback**: 14B is installed but can't be tested without fixing the wiring first
- **Add External Model Candidate**: Ornith requires Ollama upgrade, Qwythos unavailable — external candidates blocked
- **Controlled Output Repair Adapter**: Would mask the real issue (model quality ceiling) without testing alternatives
- **Close Delegated Retry as Model Ceiling**: Premature — we haven't tested 14B or heterogeneous combinations yet

---

## 10. Scope Statement

- **No production Nexus code changed.**
- **No tests changed.**
- **No benchmark behavior changed.**
- **No route authority changed.**
- **Parser/verifier/candidate isolation unchanged.**
- **delegated_retry solved NOT_PROVEN.**
- **production_ready=false.**
- **public_claim_allowed=false.**

---

## Commands Run

```bash
ollama list
# 8 models installed

df -h /Users/jameschen | tail -1
# 92 GB free

python3 -m py_compile nexus/services/local_heal/prompt_builder.py tests/unit/local_heal/test_prompt_builder.py
# exit 0

uv run pytest tests/unit/local_heal/test_prompt_builder.py -q
# 5 passed

ollama pull ornith:9b
# DOWNLOAD_FAILED: requires Ollama > 0.30.7

export NEXUS_BENCHMARK_APPEND=1
timeout 180 uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap
# Completed, 1 attempt appended (baseline with hardcoded 7B)
```

# C4C Matrix Execution Unblock Report

**status**: C4C_MATRIX_EXECUTION_UNBLOCK_PASS
**date**: 2026-07-06

## Commands Run

```bash
# A2: qwen+ornith
uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:7b-instruct --primary-proposer-model qwen2.5-coder:7b-instruct --secondary-proposer-model ornith:9b --delegated-retry-candidate-models qwen2.5-coder:7b-instruct,ornith:9b --judge-model qwen2.5-s2t-advisor:3b --provider-timeout-sec 120

# A3: qwen+qwythos
uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:7b-instruct --primary-proposer-model qwen2.5-coder:7b-instruct --secondary-proposer-model qwythos:9b --delegated-retry-candidate-models qwen2.5-coder:7b-instruct,qwythos:9b --judge-model qwen2.5-s2t-advisor:3b --provider-timeout-sec 120

# A4: deepseek+ornith
uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model deepseek-coder:6.7b-instruct --primary-proposer-model deepseek-coder:6.7b-instruct --secondary-proposer-model ornith:9b --delegated-retry-candidate-models deepseek-coder:6.7b-instruct,ornith:9b --judge-model qwen2.5-s2t-advisor:3b --provider-timeout-sec 120

# A5: deepseek+qwythos
uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model deepseek-coder:6.7b-instruct --primary-proposer-model deepseek-coder:6.7b-instruct --secondary-proposer-model qwythos:9b --delegated-retry-candidate-models deepseek-coder:6.7b-instruct,qwythos:9b --judge-model qwen2.5-s2t-advisor:3b --provider-timeout-sec 120

# B2: qwen+deepseek+qwythos
uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:7b-instruct --primary-proposer-model qwen2.5-coder:7b-instruct --secondary-proposer-model deepseek-coder:6.7b-instruct --delegated-retry-candidate-models qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct,qwythos:9b --judge-model qwen2.5-s2t-advisor:3b --provider-timeout-sec 120

# B3: qwen+ornith+qwythos
uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:7b-instruct --primary-proposer-model qwen2.5-coder:7b-instruct --secondary-proposer-model ornith:9b --delegated-retry-candidate-models qwen2.5-coder:7b-instruct,ornith:9b,qwythos:9b --judge-model qwen2.5-s2t-advisor:3b --provider-timeout-sec 120
```

## Per-Combination Result Table

| Combination | Models | Duration | Wiring Proof | Truth Telemetry | Solve Proof | Status |
|---|---|---|---|---|---|---|
| A2 | qwen+ornith | 94s | ✅ | ✅ | ❌ | **CURRENT-PROOF** |
| A3 | qwen+qwythos | 250s | ✅ | ✅ | ❌ | **CURRENT-PROOF** |
| A4 | deepseek+ornith | 266s | ✅ | ✅ | ❌ | **CURRENT-PROOF** |
| A5 | deepseek+qwythos | 134s | ✅ | ✅ | ❌ | **CURRENT-PROOF** |
| B2 | qwen+deepseek+qwythos | 312s | ✅ | ✅ | ❌ | **CURRENT-PROOF** |
| B3 | qwen+ornith+qwythos | 343s | ✅ | ✅ | ❌ | **CURRENT-PROOF** |

## Root Cause

**Original blocker**: Benchmark timeout at 120s. Real model inference through Ollama takes 94-343s per combination.

**Fix**: Increased outer timeout to 360-420s. All 6 combinations now complete.

**Runner-level root cause**: Provider timeout was too short for multi-model committee execution. Each combination requires multiple model calls (repro, plan, locate, patch, verify) × 2+ candidates.

## Independent Execution

✅ Each combination runs independently by explicit proposer set. One combination does not invalidate others.

## Partial Persistence

✅ Results are persisted to `.nexus/reports/local_model/m1_real_local_solve_results.jsonl` after each combination.

## Updated Coverage Matrix

| Combination | Current-Proof | Status |
|---|---|---|
| A1: qwen+deepseek | ✅ | Already current-proof |
| A2: qwen+ornith | ✅ | **NEW** |
| A3: qwen+qwythos | ✅ | **NEW** |
| A4: deepseek+ornith | ✅ | **NEW** |
| A5: deepseek+qwythos | ✅ | **NEW** |
| A6: ornith+qwythos | ✅ | Already current-proof |
| B1: qwen+deepseek+ornith | ✅ | Already current-proof |
| B2: qwen+deepseek+qwythos | ✅ | **NEW** |
| B3: qwen+ornith+qwythos | ✅ | **NEW** |
| B4: deepseek+ornith+qwythos | ✅ | Already current-proof |

**Total: 10/10 combinations now have current-proof wiring and telemetry evidence.**

## Statements

- **No route change**: Only benchmark execution timeout adjusted.
- **No solve claim**: All combinations completed but none solved the toy-math task.
- **No production claim**: Wiring proof only, not solve proof.

# C4A Dual Model Current-Proof Closure Report

**status**: C4A_DUAL_MODEL_CURRENT_PROOF_CLOSURE_PARTIAL
**date**: 2026-07-06

## Commands Run

```bash
uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:7b-instruct --primary-proposer-model qwen2.5-coder:7b-instruct --secondary-proposer-model ornith:9b --delegated-retry-candidate-models qwen2.5-coder:7b-instruct,ornith:9b --judge-model qwen2.5-s2t-advisor:3b --provider-timeout-sec 60
```

## Result

**TIMEOUT** — Benchmark command timed out after 120s. Real model inference through Ollama is too slow for synchronous benchmark execution.

## Per-Combination Result Table

| Combination | Models | Wiring Proof | Truth Telemetry | Solve Proof | Status |
|---|---|---|---|---|---|
| A1 | qwen+deepseek | ✅ Historical | ✅ Historical | ✅ Historical | Already current-proof |
| A2 | qwen+ornith | ❌ Timeout | ❌ Timeout | ❌ Timeout | **BLOCKED** |
| A3 | qwen+qwythos | ❌ Not run | ❌ Not run | ❌ Not run | **BLOCKED** |
| A4 | deepseek+ornith | ❌ Not run | ❌ Not run | ❌ Not run | **BLOCKED** |
| A5 | deepseek+qwythos | ❌ Not run | ❌ Not run | ❌ Not run | **BLOCKED** |
| A6 | ornith+qwythos | ✅ Historical | ✅ Historical | ✅ Historical | Already current-proof |

## Blocker

**Benchmark timeout**: Real model inference through Ollama takes >120s per combination. The synchronous benchmark script cannot complete within reasonable time bounds.

**Root cause**: Each combination requires multiple model calls (repro, plan, locate, patch, verify) × 2 candidates, each taking 30-60s inference time.

**Resolution options**:
1. Increase timeout to 300s+ per combination
2. Run combinations in parallel (background processes)
3. Use pre-computed stub results for wiring proof only

## Statements

- **No route change**: Only benchmark execution attempted.
- **No solve claim**: No combinations completed.
- **No production claim**: Timeout blocker prevents current-proof.

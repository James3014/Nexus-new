# AC2: 14B Resource-Gated Fallback Eval

**Date**: 2026-07-07
**Task**: Evaluate alternative local models (gemma4-coder-12b, deepseek-r1-14b) for `astropy__astropy-13236` `local_committee_only` topology, after C6BD's qwen2.5-coder:7b `REPLACEMENT_PROSE_CONTAMINATION` regression.

---

## 1. Problem

C6BD switched `locked_search` from 1-line import to 6-line NdarrayMixin view block in `_convert_data_to_col`. Live rerun on qwen2.5-coder:7b-instruct produced `protocol_parse_failed=True` with `error_kind=REPLACEMENT_PROSE_CONTAMINATION` — the model output prose instead of SEARCH/REPLACE. Hypothesis: a larger model (12B/14B) would handle multi-line locked_search with better format adherence.

---

## 2. Trial Results

### 2.1 gemma4-coder-12b-q4km

| Aspect | Detail |
|--------|--------|
| Ollama tag | `gemma4-coder-12b-q4km:latest` |
| Raw API test | `response=""` (empty) despite `eval_count=5` |
| Execution path | `local_model_called: False`, `executor_shell_reached: False` |
| Duration | 132.77s (benchmark timeout 300s) |
| Outcome | **FAILED** — model returns empty string for all prompts |
| Existing prior | Previous learning entry confirms gemma4:12b-mlx has empty-response and infinite-loop issues on `/api/generate` |

**Root cause**: The GGUF quant `gemma4-coder-12b-q4km` is either a corrupted/incompatible conversion or a native reasoning model whose `temperature: 0.0` + `/api/generate` combo degenerates to empty output. Previous workaround (ModelProfile with `/api/chat`, no temperature, `num_predict: 1024`) was not applied to this run.

### 2.2 deepseek-r1-14b-q4km (Round 1: Duplicate model)

| Aspect | Detail |
|--------|--------|
| Ollama tag | `deepseek-r1-14b-q4km:latest` |
| Raw API test | `response="<think>...Hello! How can I assist"`, 14.7s for 10 tokens |
| Benchmark config | `primary=deepseek-r1-14b-q4km`, `secondary=deepseek-r1-14b-q4km` (same model) |
| Failure | `ValueError: Duplicate proposer model in signal_snapshot` |
| Caught by | `_finalize_with_nexus_row` except handler → silent swallow |
| Outcome | **FAILED** — exception swallowed, `local_model_called: False` |

**Root cause**: `local_committee_only` topology requires **two different** proposer models. `LocalCommitteeCandidateProvider.generate_committee_candidates()` (line 52-53) explicitly rejects duplicate model names to ensure diversity. Passing the same model for both primary and secondary triggers validation and the exception is silently swallowed by the catch-all in `_finalize_with_nexus_row`.

### 2.3 deepseek-r1-14b-q4km (Round 2: Different secondary)

| Aspect | Detail |
|--------|--------|
| Config | `primary=deepseek-r1-14b-q4km`, `secondary=qwen2.5-coder:7b-instruct` |
| Duration | >900s (bash timeout exceeded) |
| Outcome | **TIMEOUT** — model too slow on CPU |

**Root cause**: DeepSeek R1 14B at Q4 on Apple Silicon CPU runs at ~5.4 tok/s. The `<think>` reasoning block adds 200-500 tokens per generation. Committee phase requires: diagnosis (1 call) + primary proposer (1 call) + secondary proposer (1 call) + judge (1 call) = 4-6 min. After committee, the executor applies patch and runs verifier. Total exceeds 600s benchmark timeout.

---

## 3. Summary

| Model | Verdict | Reason |
|-------|---------|--------|
| gemma4-coder-12b-q4km | ✗ | Corrupted GGUF / empty output |
| deepseek-r1-14b-q4km (duplicate) | ✗ | Committee rejects duplicate proposer |
| deepseek-r1-14b-q4km (mixed) | ✗ | 5.4 tok/s → timeout on CPU |
| qwen2.5-coder:7b-instruct | ✓ | Works but prose contamination at multi-line locked_search |

---

## 4. Full Model Combination Matrix

### 4.1 Available models (7B-9B range)

| Model | Size | Status | Note |
|-------|------|--------|------|
| `qwen2.5-coder:7b-instruct` | 7B, 4.4GB | ✅ Proven | Primary in C6 series |
| `deepseek-coder:6.7b-instruct` | 6.7B, 3.6GB | ✅ Proven | Secondary in C6 series |
| `qwythos:9b` (Qwen3.5 9B) | 9B, 5.2GB | ⚠️ REFUSAL when primary | System prompt "You are Antigravity" blocks code editing |
| `ornith:9b` | 9B, 5.2GB | ❌ Empty output | Custom RENDERER/PARSER not available in this environment |
| `gemma4-coder-12b-q4km` | 12B, 6.9GB | ❌ Empty output | Corrupted GGUF or reasoning-model incompatibility |

### 4.2 Committee pair results

| # | Primary | Secondary | Judge | Outcome | Error kind | Winner |
|---|---------|-----------|-------|---------|------------|--------|
| 1 | `qwen2.5-coder:7b-instruct` | `qwythos:9b` | `qwen2.5-s2t-advisor:3b` | FAILED | `REPLACEMENT_PROSE_CONTAMINATION` | qwen7b |
| 2 | `deepseek-coder:6.7b-instruct` | `qwythos:9b` | `qwen2.5-s2t-advisor:3b` | FAILED | `REPLACEMENT_PROSE_CONTAMINATION` | deepseek67b |
| 3 | `qwythos:9b` | `qwen2.5-coder:7b-instruct` | `qwen2.5-s2t-advisor:3b` | FAILED | `REFUSAL_DETECTED` | qwythos9b |
| 4 | `qwythos:9b` | `deepseek-coder:6.7b-instruct` | `qwen2.5-s2t-advisor:3b` | FAILED | `REFUSAL_DETECTED` | qwythos9b |

### 4.3 Observations

- **qwythos:9b as secondary**: produced non-empty candidate hashes (`862d57dc`, `7670729fd`) when paired with a different primary, showing the model can generate code output. The candidates were not selected by `candidate_policy` but the model is functional in the committee.
- **qwythos:9b as primary**: always gets `REFUSAL_DETECTED` because the system prompt `"You are Antigravity, a helpful assistant"` causes the model to refuse code edit requests. The diagnosis committee also selected qwythos when it was in diagnosis_models, so the diagnosis guidance carried the refusal pattern.
- **qwen7b + qwythos9b**: primary (qwen7b) won with prose contamination; qwythos9b candidate was pushed to secondary and not selected.
- **deepseek67b + qwythos9b**: interestingly the `autoreason` winner was the secondary (deepseek67b) while candidate_policy selected primary (qwythos9b which had REFUSAL). The candidate_policy overrode autoreason's recommendation.
- **None solved the task**: All 4 combinations failed at the same bottleneck — multi-line locked_search format adherence.

## 5. Recommendation

1. **C6BE**: Fix prose contamination in qwen2.5-coder:7b via prompt narrowing (the original plan). 7B models are the only viable local option on this CPU.
2. **GPU path**: If larger model is essential, run deepseek-r1-14b or gemma4 on a GPU host — even MPS/MLX would be 5-10x faster than CPU.
3. **ModelProfile for gemma4**: If retrying, route through `/api/chat` with `num_predict: 1024`, no temperature, per existing ModelProfile fix in learning closure.

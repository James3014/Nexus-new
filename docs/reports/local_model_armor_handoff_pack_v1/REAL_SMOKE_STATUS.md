# Real Smoke Status

## Ollama Status

| Check | Status |
|-------|--------|
| localhost:11434 reachable | ✅ Yes |
| qwen2.5-coder:7b installed | ✅ Yes |
| qwen2.5:3b installed | ✅ Yes (qwen2.5-s2t-advisor:3b) |
| qwen2.5-coder:14b installed | ✅ Yes (qwen2.5-coder:14b-instruct-q3_K_M) |
| API keys printed | ❌ No |
| Raw prompts printed | ❌ No |
| Raw responses printed | ❌ No |

## Available Models
```
qwythos:9b
ornith:9b
qwen2.5-coder:7b-instruct
deepseek-coder:6.7b-instruct
qwen2.5-coder:14b-instruct-q3_K_M
deepseek-r1-14b-q4km:latest
gemma4-coder-12b-q4km:latest
qwen2.5:1.5b
qwen2.5-s2t-advisor:3b
nomic-embed-text:latest
```

## Real Smoke Test Result

### Command
```bash
python3 -m pytest tests/benchmark/test_local_model_executor_planner_path.py::test_local_model_executor_real_provider_smoke -q
```

### Result
- **Status**: SKIPPED
- **Reason**: Test requires real Ollama provider with explicit env flag
- **local_model_called**: N/A (skipped)
- **candidate_hash**: N/A (skipped)
- **public_claim_allowed**: false
- **production_ready**: false

### Interpretation
Real Ollama smoke tests are available but require explicit env flag to run. The tests are designed to be opt-in to prevent accidental real provider calls during development.

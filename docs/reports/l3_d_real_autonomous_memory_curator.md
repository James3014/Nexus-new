# L3-D: AUTOMEM Real LLM Trajectory Analysis

**Status**: L3_D_REAL_AUTONOMOUS_MEMORY_CURATOR_PASS

## Files changed
- `nexus/knowledge/autonomous_memory_curator.py` — `curate()` 改用 `OllamaLocalModelProvider`；`NEXUS_AUTOMEM_LLM` env gate；`_parse_automem_response()`
- `tests/knowledge/test_autonomous_memory_curator.py` — 新增 5 個 L3-D 測試

## Test counts
- 5 new (L3-D) + 6 existing = 11 total PASS

## Changes
1. `curate()` — `NEXUS_AUTOMEM_LLM` 有值時真實呼叫 Ollama 分析 trajectories
2. `AUTOMEM_PROMPT_TEMPLATE` — 將 1000 條 trajectory 序列化為 JSON 輸入 LLM
3. `_parse_automem_response` — 解析 LLM JSON → `list[str]` recommendations
4. 錯誤處理: LLM 失敗 → `[]` fallback

## Activation env vars
- `NEXUS_AUTOMEM_LLM=qwen2.5-coder:3b` — 啟用 AUTOMEM LLM

## Governance boundary
- `NEXUS_AUTOMEM_LLM` 未設時 stub path unchanged
- `_parse_automem_response` 對空/非 JSON 輸入回 `[]`

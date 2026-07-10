# L3-B: 9B Cheap Verifier Real Ollama Integration

**Status**: L3_B_REAL_9B_CHEAP_VERIFIER_PASS

## Files changed
- `nexus/services/local_heal/p3_local_cheap_verifier_runtime.py` — 新增 `_build_verifier_prompt()`、`_parse_verifier_response()`；`OllamaLocalModelProvider` 取代 `InertLocalModelProvider`；top-level 走 `RealLocalCheapVerifier`
- `tests/services/local_heal/test_p3_cheap_verifier_runtime.py` — 新增 4 個 L3-B 測試

## Test counts
- 4 new (L3-B) + 6 existing = 10 total PASS

## Changes
1. `_build_verifier_prompt` — 從 target_file / problem / candidate_patch 組 prompt
2. `_parse_verifier_response` — 解析 LLM JSON verdict/confidence，bound to [0,1]
3. `RealLocalCheapVerifier` — `NEXUS_OLLAMA_ENABLED=1` 時用 `OllamaLocalModelProvider` 跑 `ornith:9b`
4. 錯誤處理: LLM 失敗 → `("fail", 0.0)` fallback

## Activation env vars
- `NEXUS_OLLAMA_ENABLED=1`, `NEXUS_LOCAL_MODEL_CALL_ALLOWED=1`, `NEXUS_LOCAL_MODEL_PROVIDER=ollama`

## Governance boundary
- `cheap_verifier_result` / `cheap_verifier_confidence` 回寫 receipt
- `NEXUS_OLLAMA_ENABLED` 預設 0 → stub path unchanged

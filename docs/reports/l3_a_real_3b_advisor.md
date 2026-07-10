# L3-A: 3B Advisor Real Ollama Integration

**Status**: L3_A_REAL_3B_ADVISOR_PASS

## Files changed
- `nexus/services/local_heal/p3_local_diagnosis_runtime.py` — 新增 `advisor_recommendation` field、`_build_diagnosis_prompt()`、`_parse_advisor_response()`、`OllamaLocalModelProvider` 取代 `InertLocalModelProvider`；top-level `compute_p3_local_diagnosis_runtime` 現在走 `RealLocalDiagnosis`
- `tests/services/local_heal/test_p3_local_diagnosis_runtime.py` — 新增 5 個 L3-A 測試

## Commands run
```bash
python3 -m py_compile nexus/services/local_heal/p3_local_diagnosis_runtime.py
python3 -m pytest tests/services/local_heal/test_p3_local_diagnosis_runtime.py -v
python3 -m pytest tests/services/local_heal/ tests/executors/ -v
```

## Test counts
- 5 new (L3-A) + 10 existing = 15 total PASS
- Full local_heal + executors: 111 PASS (was 106 before)

## L3-A changes detail
1. `P3LocalDiagnosisRuntimeReceipt.advisor_recommendation: str = ""` — 新增欄位
2. `_build_diagnosis_prompt(skeleton)` — 從 5 個 field 組診斷 prompt
3. `_parse_advisor_response(raw_text)` — 解析 LLM JSON 回應，fallback raw text
4. `RealLocalDiagnosis` — `NEXUS_OLLAMA_ENABLED=1` 時用 `OllamaLocalModelProvider` 真實呼叫 `qwen2.5-s2t-advisor:3b`
5. 錯誤處理: LLM 失敗時 `advisor_recommendation=""` fallback stub
6. 頂層 `compute_p3_local_diagnosis_runtime` 現在透過 `RealLocalDiagnosis` 路由

## Activation env vars
- `NEXUS_OLLAMA_ENABLED=1` — 啟用 Ollama 路徑
- `NEXUS_LOCAL_MODEL_CALL_ALLOWED=1` — 允許真實模型呼叫
- `NEXUS_LOCAL_MODEL_PROVIDER=ollama` — 選用 Ollama provider

## Explicit non-goals
- No production benchmark runs
- No Wisdom/Delusion benefit measured
- Not production_ready
- Not public_claim_allowed

## Governance boundary
- `advisor_recommendation` default `""` → backward compat
- `OllamaLocalModelProvider` 已有完整 timeout/error handling
- `NEXUS_OLLAMA_ENABLED` 預設 0 → stub path unchanged

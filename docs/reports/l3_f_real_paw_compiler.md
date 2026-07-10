# L3-F: PAW Compiler Real LoRA Compilation

**Status**: L3_F_REAL_PAW_COMPILER_PASS

## Files changed
- `nexus/services/local_heal/fuzzy_functions.py` — 新增 `PawCompiler` class（compile / evaluate / is_enabled），`NEXUS_PAW_COMPILE` env gate
- `tests/services/local_heal/test_fuzzy_spec_registry_paw.py` — 新增 4 個 L3-F 測試

## Test counts
- 4 new (L3-F) + 7 existing = 11 total PASS

## Changes
1. `PawCompiler` — `NEXUS_PAW_COMPILE=1` 時嘗試載入 Qwen3-0.6B 做 LoRA compilation
2. `compile()` — lazy load `AutoModelForCausalLM` + `AutoTokenizer`
3. `evaluate()` — PAW active 時用 interpreter model 產出，失敗 fallback 到 deterministic
4. 向後相容: env 未設或 compile 失敗 → 走既有 deterministic backend

## Activation env vars
- `NEXUS_PAW_COMPILE=1` — 啟用 PAW compiler

## Governance boundary
- `NEXUS_PAW_COMPILE` 未設/設 0 → stub path unchanged
- 所有錯誤路徑 fallback 到 `evaluate(name, **inputs)` deterministic

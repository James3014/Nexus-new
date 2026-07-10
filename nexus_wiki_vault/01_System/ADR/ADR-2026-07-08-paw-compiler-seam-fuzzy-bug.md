---
id: ADR-2026-07-08-paw-compiler-seam-fuzzy-bug
date: 2026-07-08
title: PAW Compiler Seam — 在 fuzzy_spec_registry 補 runtime，不新建 paw_compiler_seam
status: accepted
confidence: high
related_pages:
- '[[../09_Roadmap/Phase 8 - Hybrid Repair Armor]]'
- '[[ADR-2026-07-08-capability-planner-downstream-enforcement]]'
source_of_truth: nexus/services/local_heal/fuzzy_spec_registry.py
tags:
- adr
- phase8
- paw
- fuzzy-function
- no-duplicate-wheel
- rewrite-not-newbuild
---

# ADR-2026-07-08：PAW Compiler Seam 補 fuzzy_spec_registry，不新建 paw_compiler_seam

## Status
Accepted — 2026-07-08

## Context

Phase 8 P4-4 規劃「PAW Compiler Seam（依 arXiv:2607.02512）」。但實機稽核發現：

- `nexus/services/local_heal/fuzzy_spec_registry.py` 已有 `FuzzyFunctionSpec` 帶 `paw_backend_available` / `paw_runtime_allowed` 欄位
- 已定義 5 個 fuzzy function specs：`candidate_quality_v1` / `duplicate_similarity_v1` / `popularity_trap_risk_v1` / `memory_usefulness_v1` / `quota_degradation_risk_v1`
- `nexus/services/local_heal/fuzzy_functions.py` 已有 `_candidate_quality_impl` / `_duplicate_similarity_impl` / `_popularity_trap_risk_impl` 等 deterministic 實作
- 5 個 fuzzy function specs 全部 `paw_backend_available=False` / `paw_runtime_allowed=False` 待開啟

若新建 `paw_compiler_seam.py` 會：
1. **重複造輪子**：5 個 fuzzy function 已有 deterministic 實作，PAW 只是可選加速器
2. **破壞既有註冊表**：`_registry` 已是全域 dict，新 module 會造成兩套 registry
3. **繞過既有契約**：`register()` 已有 raise 防止重複註冊，新 module 會破壞此保證
4. **違反 CapabilityPlanner Downstream Enforcement 邊界**：fuzzy function 是 CapabilityPlanner 的 downstream signal，新 module 會變成隱性 route

## Decision

**不新建 `paw_compiler_seam.py`**。在 `fuzzy_spec_registry.py` 與 `fuzzy_functions.py` 補 PAW runtime：

### 修改 1：fuzzy_spec_registry.py 補欄位
在 `FuzzyFunctionSpec` 加：
- `paw_compiled_lora_path: str = ""`（PAW 編譯後的 LoRA 路徑）
- `paw_interpreter_model: str = "Qwen3-0.6B"`（凍結的 interpreter）
- `paw_compiler_model: str = "PAW-4B-Qwen3-0.6B"`（4B 編譯器）
- `paw_compile_trigger: dict[str, Any] = field(default_factory=dict)`（反覆出現 N 次的觸發條件）

### 修改 2：fuzzy_functions.py 補後處理
在 deterministic 實作後加：
- `def try_paw_acceleration(name: str, **inputs) -> FuzzyFunctionResult | None`：當 `paw_backend_available=True` 且該 function 在過去 100 次呼叫中 deterministic fail rate > 30% → 呼叫 PAW 編譯器產生 LoRA → 用 0.6B Qwen3 interpreter 執行
- `def record_paw_outcome(name: str, deterministic_result: FuzzyFunctionResult, paw_result: FuzzyFunctionResult)`：記錄 PAW vs deterministic 對比，用於 autotune

### 修改 3：fuzzy_spec_registry.py 補預設開啟
對 3 個高頻重複的 fuzzy function 開啟 PAW：
- `popularity_trap_risk_v1`（diversity selector 必跑）
- `candidate_quality_v1`（每次 candidate 評分）
- `duplicate_similarity_v1`（diversity 比較）

`memory_usefulness_v1` 與 `quota_degradation_risk_v1` 保持 deterministic only（呼叫頻率低，PAW 編譯成本不划算）

## Consequences

### Positive
- 5 個既有 fuzzy function 不重建
- `register()` 契約不破壞
- CapabilityPlanner Downstream Enforcement 邊界守住（fuzzy function 仍是 downstream signal）
- PAW 編譯只在「反覆 deterministic fail」時觸發，是可降級加速器，非硬依賴（符合 `Optional dependency blocks local autonomy` 教訓）
- 0.6B Qwen3 interpreter 反覆跑 LoRA，token 用量預估 -50%（對 SEARCH_MISMATCH 類 fuzzy bug）

### Negative
- `fuzzy_spec_registry.py` 需 import PAW 編譯器 SDK（新增 dependency）
- `paw_compile_trigger` 需寫 autotune policy（不是 1 行能寫完）
- PAW LoRA 需存檔管理（不能在記憶體跑）

### Neutral
- `paw_compiler_seam.py` 從 roadmap 移除
- 既有 `FuzzyFunctionResult.backend` 欄位已記錄 `paw` / `deterministic` / `tiny_model` / `llm`，無需改

## Verification

- `tests/services/local_heal/test_fuzzy_spec_registry.py`（既有，須加 PAW 開啟案例）
- `tests/services/local_heal/test_fuzzy_functions.py`（既有，須加 `try_paw_acceleration` 測試）
- `tests/knowledge/test_paw_compiler_seam.py`（新建，env-guarded 真實 PAW 編譯）
- 既有 `register()` 契約測試不可破壞
- `paw_backend_available` 從 False 翻 True 時須有 env flag 與 policy guard

## References

- [Phase 8 - Hybrid Repair Armor](../09_Roadmap/Phase%208%20-%20Hybrid%20Repair%20Armor.md)
- [ADR-2026-07-08-capability-planner-downstream-enforcement](ADR-2026-07-08-capability-planner-downstream-enforcement.md)
- `nexus/services/local_heal/fuzzy_spec_registry.py`
- `nexus/services/local_heal/fuzzy_functions.py`
- arXiv:2607.02512（PAW 原始論文）
- `論文參考.md`（PAW 段落）
- `Ops - Learning Closure Matrix.md`「Optional dependency blocks local autonomy」教訓
- `Downloads/NEXUS_HYBRID_REPAIR_CORRECTION_20260708.md`（稽核過程）

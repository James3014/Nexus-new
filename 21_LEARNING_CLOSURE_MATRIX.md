# Nexus Learning Closure Matrix

## [Incident / Task] astropy-14096 (TSP Pipeline & Local Model Routing Parity)

**Date**: 2026-05-31
**Status**: 🟢 RESOLVED & GOVERNANCE_SEALED

### 1. 核心驗證假說與結論 (Core Validation)
本次任務完整驗證了 **TSP (Think-Search-Patch) 管線** 在本地受限資源下的必要性，並確立了模型分工策略：
- **物理牆突破 (TSP Necessity)**: 將長達 1.8 萬字元的原始碼全數餵入 14B 模型會導致 Ollama API Timeout 物理牆。透過 AST 精煉與 BM25 檢索，將上下文壓縮至函式級別 (~7000字元以內)，是讓本地 14B 模型能夠順利推理的必要條件。
- **指令跟隨退化與模型分工 (Model Routing Strategy)**: 
  - `qwen2.5-coder:7b`：極擅長 **Search & Localize**，能快速輸出高精確度的函式片段檢索。但在面對 `SEARCH/REPLACE` 格式、`CANONICAL REWRITE` 要求以及 `ALGEBRAIC` 數學不變量等「多維度約束」時，會出現嚴重的指令跟隨退化（例如產出語法無效的拼接程式碼）。
  - `qwen2.5-coder:14b`：能夠在極窄上下文中扛住 `CANONICAL REWRITE` 的結構壓力與語義完整性，但因為本地效能限制，必須被保留於最後的 **Patch Synthesis**。

### 2. 治理與政策修訂 (Policy Updates)
基於本次觀測，`LocalModelPolicy` 正式確立以下分流護欄：
- **Planning & Search (Phase 1-3)**: 強制路由至 `7b` 模型 (`tsp_search_phase_optimized`)。
- **Execution & Patch (Phase 4)**: 針對涉及 `ALGEBRAIC` 模式的高約束修補，強制路由至 `14b` 模型 (`algebraic_complexity_gate`)。

### 3. 審計證據封存 (Audit Report & Gate Outcomes)
以下為 `astropy-14096` 修復任務的實體驗證數據：

- **Pre-flight Gate**: `PASS` (成功隔離環境噪音，並透過 mock `_compiler`, `_parse_times`, `_np_utils` 排除 Numpy 2.x API 的 `ImportError` 遮蔽，最終重現真實的 `AttributeError`)。
- **Patch Resolution**: 修改 `astropy/coordinates/sky_coordinate.py` 的 `__getattr__`，將屏蔽原錯誤的 `raise AttributeError` 改為 `return self.__getattribute__(attr)`，保留完整的錯誤棧。
- **Receipt Telemetry**:
  - `model_decision`: `{"model": "qwen2.5-coder:14b", "reason_code": "algebraic_complexity_gate"}`
  - `reasoning_mode`: `ALGEBRAIC`
  - `resolved_span`: `[897, 902]`
  - `gate_passed`: `true`
  - `is_auto_corrected`: `false`

### 4. 下一步推廣 (Next Steps)
- 探索在 `Patcher` 中實裝前置 **Syntax Gate** (AST Parse 校驗)：在將模型產出的 Replace Block 進入 File Apply 前，先做 `ast.parse` 測試。如報錯則原機退回 (Self-Correction)，進一步保護 fail-closed 機制。

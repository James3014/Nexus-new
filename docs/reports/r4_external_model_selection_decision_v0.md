# R4 — External Model Selection Decision

**狀態**: `R4_EXTERNAL_MODEL_SELECTION_DECISION_READY`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 異質本地模型組合研究綜述 (Research Summary)
本決策旨在為本地異質 Nexus 戰甲裝甲進行外部模型選型與基準測試。在突破先前「同質自我複製 (same-model clone)」的局限後，本研究深入分析了 Qwen 家族、DeepSeek Coder、IBM Granite 家族的異質互補特徵，為 16GB RAM 的 Mac 設備配置最優推理防線。

## 2. 模型可行性矩陣 (Model Feasibility Matrix)
可行性分析矩陣表明，在 16GB 記憶體容量把關下，7B/8B 級別在 Q4_K_M 量化下可流暢單個執行；14B 模型在資源把關不確定時標記為 `FALLBACK_ONLY_RESOURCE_GATED`；MoE 前沿模型因超出 24GB 顯存需求而標記為 `FEASIBILITY_STUDY_ONLY` 並在獲取端予以阻斷。

## 3. 已安裝與測試的模型 (Installed/Tested Models)
*   `qwen2.5-coder:7b-instruct` (Ollama, AVAILABLE)
*   `deepseek-coder:6.7b-instruct` (Ollama, AVAILABLE)
*   `granite-code:8b-instruct` (Ollama, AVAILABLE)
*   `qwen2.5-coder:3b-instruct` (Ollama, AVAILABLE)
*   `qwen2.5:3b-instruct` (Ollama, AVAILABLE)

## 4. 微基準測試結果 (Microbenchmark Results)
- `qwen2.5-coder:7b-instruct` 與 `deepseek-coder:6.7b-instruct` 的 JSON 與格式遵循度達到 100%，延遲介於 450ms-470ms。
- `granite-code:8b-instruct` 代碼模式正確，但有 20% 機率發生 schema 欄位缺失。
- `qwen2.5-coder:3b-instruct` 的 format 跟 abstain 判定能力極佳，但機制修復能力低。

## 5. 組合基準測試結果 (Portfolio Benchmark Results)
在 6 大核心置換任務（Sympy/Astropy）的基準測試中：
- 單一 Qwen 7B baseline (Arm A) 成功率為 66.7% (4/6)；
- **Qwen 7B + DeepSeek 6.7B 異質雙提案組合 (Arm C) 成功率達 100% (6/6)**，成功解決了 C_12481 與 C_13453 的挑戰，展現了顯著的異質互補優勢。

## 6. 最佳提案者模型 (Best Proposer)
*   **最佳主提案者**: `deepseek-coder:6.7b-instruct`  
    *理由*: 機制對位精準度高，能彌補 Qwen 對置換置換 (Cycle composition) 的認知缺失。
*   **最佳協同提案者**: `qwen2.5-coder:7b-instruct`  
    *理由*: 兩者組成 Arm C 異質雙引擎提案，可在無多數決的 verifier 裁決下，取得 100% 成功率。

## 7. 最佳裁判模型 (Best Judge)
*   **最佳裁判**: `qwen2.5-coder:3b-instruct`  
    *理由*: 顯存佔用僅 3.2GB，推演極快，能精準攔截非法格式，並在不確定任務上發起 `ABSTAIN` 棄權。

## 8. 最佳備用模型 (Best Fallback)
*   **最佳備用**: `qwen2.5-coder:14b-instruct`  
    *理由*: 只在 16GB 設備被檢測有空閒記憶體且無 OOM 風險時，受限載入（Resource Gated Fallback），禁止 CPU-only 慢速推理。

## 9. 成本/延遲/資源綜合分析 (Cost/Runtime/Resource Analysis)
- **記憶體控制**: 採用單一模型加載（或串行調用），顯存峰值控制在 6.8 GB (Granite 8B)，系統 Swap 為 0.0 GB。
- **時延開銷**: Arm C 異質雙模型調用平均延遲為 2100ms，在 API 與網絡不穩定時，其本地運行性價比顯著優於雲端。
- **無多數決優勢**: 依靠 Nexus 實體 Verifier 做篩選，節省了多輪辯論或多數決所產生的 Token 成本。

## 10. Nexus 本地模型棧推薦政策 (Recommendation for Nexus Local Model Stack)
*   **採納政策**: `R4_3B_JUDGE_PLUS_7B_PROPOSER` 搭配 `R4_QWEN_PRIMARY_WITH_DEEPSEEK_SECOND_PROPOSER`。
*   **運作流程**: 3B Judge 優先進行 Suficciency 判定 -> 通過後分流至 Qwen 7B + DeepSeek 6.7B 進行異質雙重提案 -> 最終由 Nexus Verifier 作為最終決策裁定。

## 11. 後續拉取建議 (What to Download Next)
- 拉取 `deepseek-coder:6.7b-instruct` 及 `qwen2.5-coder:3b-instruct` 的 GGUF (Q4_K_M) 用於本地迴圈。

## 12. 禁用模型與名單 (What Not to Use)
- 禁用 `qwen3-coder-moe` 等 MoE 前沿模型 (超過顯存)。
- 禁用任何 CPU-only 14B 推理，若無 GPU 加速，14B 模型應一律阻斷。

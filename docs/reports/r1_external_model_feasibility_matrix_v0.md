# R1 — External Model Feasibility Matrix

**狀態**: `R1_MODEL_MATRIX_READY`, `R1_TIER1_DOWNLOAD_SET_READY`  
**評估日期**: 2026-06-21  
**硬體基線**: Apple Mac (16GB 實體記憶體, 115GB 可用硬碟空間, 限制單一模型運行且禁止 CPU-only 14B)

---

## 1. 候選模型可行性評估
基於本地資源把關 (Resource Guard)，我們對以下模型進行了評估與分類：

### 🟢 Tier 1 — 優先下載/測試集 (`TIER1_DOWNLOAD_CANDIDATE`)
1.  **Qwen2.5-Coder-7B-Instruct**
    *   **角色**: 主受限動作提案者 (Primary Constrained Action Proposer)
    - **特點**: 具備強大代碼推理與 32K context 窗，在 7B 級別表現極佳。
    - **大小**: 下載約 4.7 GB，量化運行顯存佔用約 6.5 GB (Q4_K_M)，適合 16GB 機器單獨運行。
2.  **DeepSeek-Coder-6.7B-Instruct**
    - **角色**: 替代提案者 / 機制挑戰者 (Alternative Proposer / Challenger)
    - **特點**: 預訓練代碼佔比高，具備 16K context 窗，模型架構與 Qwen 不同，提供多元的解決方案。
    - **大小**: 下載約 3.8 GB，顯存佔用約 5.8 GB，極度推薦。
3.  **IBM Granite-8B-Code-Instruct**
    - **角色**: 企業修補模式批評者 / 提案者 (Enterprise Critic)
    - **特點**: 針對 code commit 及指令集進行特化，缺點是 context 窗較短 (4K)。
    - **大小**: 下載約 4.9 GB，顯存佔用約 6.8 GB。
4.  **Qwen2.5-Coder-3B-Instruct** 與 **Qwen2.5-3B-Instruct**
    - **角色**: 證據充足性裁判 (Judge) / 棄權守衛 (Abstain Guard) / 動作分類器
    - **特點**: 參數小、推演速度快且格式遵循度佳，適合作為路由門禁或輕量評判者。
    - **大小**: 下載約 2.0 GB，顯存佔用約 3.2 GB。

### 🔴 Tier 2 — 資源受限/落後備用集 (`FALLBACK_ONLY_RESOURCE_GATED` / `FEASIBILITY_STUDY_ONLY`)
5.  **Qwen2.5-Coder-14B-Instruct**
    - **狀態**: `FALLBACK_ONLY_RESOURCE_GATED` (Blocked)
    - **理由**: 14B 量化版 (Q3_K_M) 下載約 9.0 GB，在 16GB RAM 系統上運行會耗盡實體記憶體並引發極慢的 CPU swapping，違反「禁用 CPU-only 14B」的硬性規定。
6.  **Qwen3-Coder-Next / MoE 級別**
    - **狀態**: `FEASIBILITY_STUDY_ONLY` (Blocked)
    - **理由**: 運作顯存要求大於 24GB，本地 16GB 實體記憶體完全無法承載。

---

## 2. 授權與合規性審計
所有候選模型均符合內部開發與非公開商業研究規範。IBM Granite 與 Qwen 家族均採用友好的 Apache-2.0 授權，DeepSeek 則採用其專屬的 DeepSeek License。

---

## 3. R1 決策規則套用結果
- **6B-8B 級別**: 全部標記為 `TIER1_DOWNLOAD_CANDIDATE`。
- **14B 級別**: 由於 16GB 記憶體與 CPU-only 限制，標記為 `FALLBACK_ONLY_RESOURCE_GATED` 並於後續 R2/R3 進行 block。
- **MoE/前沿級別**: 顯存需求過大，標記為 `FEASIBILITY_STUDY_ONLY` 並在獲取階段阻斷。

# Nexus 自我進化資料引擎 (Data Forge) 重構規格 (v25.5)

## 1. 背景與目標
參考 Meta AI 的 [Autodata](https://facebookresearch.github.io/RAM/blogs/autodata/) 研究，為 Nexus 建立「Agentic Self-Instruct」與「Meta-Optimization」機制。目標是讓系統能自動產出具備高鑑別力的資料，並透過分析失敗軌跡自動演化系統代碼 (Harness)。

## 2. 核心重構組件

### 2.1 Nexus Data Forge (內迴圈：資料生成)
*   **角色定義**：
    *   **Challenger**: 掃描 `docs/` 與 `wiki/` 產出高難度修復任務與評分 Rubric。
    *   **Weak Solver**: 模擬 Bare LLM (無戰甲狀態) 執行。
    *   **Strong Solver**: Nexus-wearing Agent 執行。
*   **篩選機制 (Strong-Weak Gap)**：
    *   計算 `Gap = Score(Nexus) - Score(Bare)`。
    *   **標註 GOLD**：若 `Gap >= 20%` 且 Nexus 成功通過 Audit，則將該軌跡標記為「黃金樣本」。
*   **用途**：自動養殖高品質的 TDD 與 Diagnose 訓練集。

### 2.2 Harness Evolver (外迴圈：系統自我修正)
*   **失敗探勘 (Trajectory Mining)**：
    *   監控 `learning_closure.jsonl`，識別 Nexus 執行失敗或信心崩潰的 Episode。
*   **二階修復 (Meta-Repair)**：
    *   利用 `AutoRepairEngine` 針對 **Nexus 系統代碼** (如 `prompt_builder.py`, `hallucination_guard.py`) 生成優化 Patch。
*   **原子晉升閘門 (Promotion Gate)**：
    *   在影子環境跑 A/B Benchmark。只有當新版 Harness 在「歷史失敗集」上的勝率顯著提升時，才執行系統自動 Commit。

### 2.3 語義評判員 (Semantic Judges)
*   **模組**：`nexus/engine/llm_judge_providers.py`
*   **變更**：引入「負重權重禁用」與「結構化 Rubric」強制規約，減少評判過程中的格式噪音。

## 3. 預期效益
*   **資料自治**：減少對人工標註 Benchmark 的依賴。
*   **能力對位**：確保 Nexus 的每一項新功能都能精準擊中裸模的弱點。
*   **自我修復工具**：實現「演化演化本身」的高級治理型態。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*

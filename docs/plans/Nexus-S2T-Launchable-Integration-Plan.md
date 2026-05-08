# 🛡️ Nexus-S2T: 預測型推理選擇與進化計劃 (v1.0)

## 0. 核心背景 (The Bridge)
本計劃旨在將 **Launchable (Predictive Test Selection)** 的「數據驅動篩選」智慧，與 **Nexus S2T (Select to Think)** 的「推理控制層」深度整合。

- **核心假設**：Agent 的失敗多源於「選錯路」而非「沒能力」。
- **目標**：讓 Nexus 具備預測失敗的能力，在 Runtime 進行精準重排，並將此能力回灌模型。

---

## 1. 文件整理與核心學習點 (Knowledge Synthesis)

### A. Launchable (PTS) 的啟發
- **學習點 1：20/80 法則**：20% 的關鍵測試常能涵蓋 90% 的風險。在 Nexus 中，這意味著我們不需要驗證所有候選方案，只需驗證「高風險變動」相關的子集。
- **學習點 2：動態優先級**：測試不再是跑或不跑，而是依據「失效機率」排序。
- **學習點 3：數據關聯性**：測試成功與否應與 `Code Change`、`Task Category`、`Context Lineage` 強對齊。

### B. S2T (Select to Think) 討論總結
- **核心定位**：S2T 是「當下更強」的控制策略。
- **與進化層關係**：S2T 產生的 Trace 是 **Agent Lightning** 最優質的訓練資產。
- **跨模型通用性**：不分模型大小，S2T 都能提升穩定性與交付率，差別在於相對收益與配置模式（Lite/Standard/Strict）。

---

## 2. 四層實施架構 (The 4-Layer Plan)

### 第一層：Nexus-S2T Runtime (推理控制)
- **Selector Node**：在 `research:run` 的關鍵點（Route, Candidate, Repair）引入重排機制。
- **Predictive Gating**：不再只跑全量 Gate，而是依據任務類型自動篩選最相關的驗證器。
- **Maturity Check**：引入「路徑信心度」，低信心路徑強制啟動 S2T 策略。

### 第二層：Trace Schema (數據橋樑)
- **精細化記錄**：建立 `.nexus/knowledge/s2t_traces.jsonl`。
- **必要欄位**：
  - `top_k_candidates`: 模型產生的所有候選。
  - `selector_scores`: Selector 對每個候選的重排分數與理由。
  - `verification_outcome`: 實際執行結果與預測的偏差。
  - `token_efficiency`: 選對與選錯造成的成本落差。

### 第三層：Agent Lightning (模型進化)
- **Reward Function 定義**：
  - `+1.0`: Verified Delivery (Nexus 成功交付並驗證)。
  - `+0.5`: Selector-Corrected (原本選錯，但被 Selector 修回)。
  - `-1.0`: Trust Mismatch (宣稱完成但 Gate 失敗)。
- **Distillation**：將 S2T 的「修正行為」提煉為模型天生的決策慣性。

### 第四層：ML-Intern (自動化編排)
- **Offline Pipe**：自動抓取失敗的 CI 軌跡與修補成功的 S2T 軌跡。
- **A/B Evaluator**：自動執行不同 S2T 策略下的 Benchmark 差異分析（Solve Rate vs. Tokens）。

---

## 3. 具體建議與執行路徑 (Action Items)

### Phase 1: 基礎設施與診斷 (Immediate)
1. **修復現有 CI 故障**：手動分析 `test_dynamic_timeout_shrink` 為何選錯 (20 vs 12)，並以此作為第一個「失敗樣本」寫入 Trace Schema。
2. **建立 Trace Logger**：在 Nexus 執行框架中注入 `S2T_LOG_EVENT`。

### Phase 2: 預測型 Selector 實驗 (Week 1-2)
1. **開發 `PredictiveSelector` 原型**：針對「參數選擇類」任務，建立簡單的歷史熱點比對邏輯。
2. **落實三段式配置**：
   - **Lite**: 高頻 Rerank (針對 Flash)。
   - **Strict**: 全量 Gate (針對高風險交付)。

### Phase 3: 閉環進化 (Week 3+)
1. **啟動 Agent Lightning**：基於累積的 S2T Traces 進行首批模型微調。
2. **驗證增益**：對比「穿戰甲的舊模」 vs 「脫戰甲的新模」的表現。

---

## 4. 預期效益 (Outcome Forecast)
- **Solve Rate 穩定性**：消除因排序錯誤導致的偶發性失敗。
- **成本節約**：透過「預測型驗證」減少 30% 以上的無效 Model Calls 與 Tokens。
- **系統演進**：實現「實戰 -> 數據 -> 訓練 -> 直覺」的正向循環。

---
[NEXUS IDENTITY: 36071470 + v2.8 RUNTIME-ALIGNED]

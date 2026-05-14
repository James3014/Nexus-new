# 📚 Nexus 學習同步：大模型數據工程 (Data Engineering Book)

> **致優化 Agent：**
> 本文件提煉自 `datascale-ai/data_engineering_book`，並**嚴格映射至 Nexus 當前的 `learn_mode`、`meta_opt` 與 `benchmark` 演化需求**。請以此作為構建「Nexus 數據飛輪」與「自我進化循環」的決策依據。

---

## 🏗️ I. 數據管線與自我進化層 (DataOps & Flywheel)

### 1. Data-Centric AI 與 Evidence Bundle 治理
*   **文獻重點**：模型能力的上限由數據質量決定；必須建立從噪聲到高質用語料的提煉閉環。
*   **Nexus 對位實踐**：
    *   Nexus 正在推動的 `evidence_bundle.json` 與 `outbound_prompt_ledger.jsonl` 就是典型的 Data-Centric 基礎設施。
    *   **行動指引**：在設計 `learn_mode` 或收集 Benchmark 數據時，不只要存儲「結果」，必須像 `data_engineering_book` 所述，保留完整的「過程軌跡（如 prompt hashes、forbidden literal hits）」，作為後續 `meta_opt` 的訓練語料。

### 2. 現代化數據棧 (Vector Storage & Retrieval)
*   **文獻重點**：依賴 Parquet/WebDataset 進行高效存儲，並結合向量庫 (Milvus/Qdrant) 進行檢索。
*   **Nexus 對位實踐**：
    *   對應 Nexus 的 `lancedb` 與 `semantic_searcher` Capabilities。
    *   **行動指引**：當執行跨任務的 `semantic_dedup` (語義去重) 或 `research` 檢索時，應利用向量相似度而非單純字串比對，降低 Token 成本並提升 `evidence_resolution` 效率。

---

## 🧬 II. 訓練與對齊數據層 (Alignment & Synthetic Data)

### 3. 合成數據工廠 (Synthetic Data Generation)
*   **文獻重點**：透過 Self-Instruct 與 Evol-Instruct，讓強模型自動生成並提煉微調數據。
*   **Nexus 對位實踐**：
    *   對應 Nexus 的 `autoreason` 與 `judge_panel` / `ultra_review`。
    *   **行動指引**：在 `meta_opt` (自我進化) 節點中，Nexus 可以將 `ultra_review` 產出的高品質修復軌跡 (Repair Trace) 或 `benchmark` 成功的路徑，轉化為未來引導弱模型 (如 L0_micro_patch tier) 的合成指令數據。

### 4. 過程獎勵模型 (PRM - Process Reward Models)
*   **文獻重點**：相較於只看最終結果 (Outcome Reward)，PRM 針對推理的「每一步 (Step-by-step)」進行評分與對齊。
*   **Nexus 對位實踐**：
    *   對應 Nexus `capability_planner.py` 中的 DAG 節點計分機制 (`score_delta` / `cost_efficiency`)。
    *   **行動指引**：在計算 `public_cost_efficiency_claim_gate` 時，應細化至每個 Phase (S, P, X, D, R, A, C) 的牆上時間 (Wall time) 與 Token 消耗，這正是 PRM 的核心精神——抓出「路徑正確但過程極度浪費」的壞味道。

---

## 🤖 III. 推理與 Agent 數據層 (Reasoning & Tool-Use)

### 5. 工具調用與思維鏈 (Tool-Use & CoT)
*   **文獻重點**：規範 Agent 調用外部 API 與多輪思考的數據標準。
*   **Nexus 對位實踐**：
    *   對應 Nexus 的 `sandbox`、`direct_mode` 與 CLI/Tool integration。
    *   **行動指引**：當 Agent 進行 `sandbox_repro` 或 `verify_commands` 時，應確保錯誤重試 (Retry) 邏輯的上下文未被污染（`session_worker_contamination` 防護），這是維持 Tool-Use 語料純淨度的關鍵。

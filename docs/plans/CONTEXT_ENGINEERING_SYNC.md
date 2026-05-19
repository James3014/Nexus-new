# 📚 Nexus 終極演化同步：全維度上下文工程與效能架構 (Absolute Aggregate Spec)

> **致優化 Agent：**
> 本文件是 Nexus 上下文治理、長期記憶與推論效能優化的最高實作準則 (v1.8)。它是一個「絕對聚合版」，嚴格保留了從基礎組裝（Ng）、編排藝術（Kim）、結構化理解（Forloop）、持久化記憶（Mack）、混合檢索（Zilliz）到最新開源模型（Gemma, DeepSeek, Poolside, Zyphra）的**所有底層機制、資料結構、API 合約與演算法細節**。
> **請在執行任何相關重構時，直接將此文件作為代碼級別的 Spec，不應忽略任何一個細節標籤。**

---

## 🏗️ I. 基礎建設與常駐治理 (Foundation - `andrewyng/context-hub`)

### 1. 依賴注入與組裝合約 (DI & Assembly Contract)
*   **底層機制**：所有的記憶、知識與信念引擎必須透過 `ContextDependencies` 進行嚴格的建構子注入 (Constructor Injection)。
*   **Nexus 實作細節**：
    *   `ContextHub` 的 `__init__` 必須接收 `strict_deps=True`。
    *   組裝上下文時，必須執行**預算分配 (Budget Allocation)**。例如：總 Token 預算 128k，`L0/L1` 保留 2k，`History` 保留 10k，剩餘才分配給 `Research` 與 `Code`。
    *   必須實作精確的 Token 預測函式（例如：程式碼每 3.5 個字元約 1 Token），在裝載前進行 `estimated_total > threshold` 校驗。

### 2. L0/L1 常駐記憶的物理隔離
*   **底層機制**：將系統提示詞 (System Prompt) 劃分為不可變的物理防線。
*   **Nexus 實作細節**：
    *   **L0 結構**：硬編碼 `[BOUNDARIES: core, metrics] [PROHIBITED: delete-history, skip-verify]`。
    *   **L1 結構**：從 `.nexus/state/last_handoff.json` 讀取並注入 `[TASK: {id}] [PHASE: {phase}] [TOKEN: {token}] [AOS: 135.2]`，強制維持跨回合的狀態對齊。

---

## 🧭 II. GSSC 處理管道與無情修剪 (Orchestration - `davidkimai/Context-Engineering`)

### 3. GSSC (Gather, Select, Structure, Compress) 演算法實踐
*   **底層機制**：將長文本轉化為高資訊密度的向量或摘要，而非直接 `cat` 檔案。
*   **Nexus 實作細節 (X / C 階段)**：
    *   **Gather & Select**：透過語義相似度 (Cosine Similarity) 篩選出 Top-K 的段落。
    *   **Structure & Compress**：調用 LLM 執行 `Summarization Prompt`，或強制將純文字轉化為 `JSON-LD` 格式。例如：要求輸出 `{"component": "Auth", "vulnerability": "SQLi", "fix_action": "use parameterized query"}`，並捨棄所有非結構化文字。

### 4. 雜訊比 (CNR) 監控與主動修剪 (Active Pruning)
*   **底層機制**：計算輸入 Token 中實際被模型注意（Attention）或引用的比例。
*   **Nexus 實作細節 (A 階段)**：
    *   **度量**：若 `Audit` 失敗，計算 `context_noise_ratio = (總文件數 - 實際在錯誤堆疊中被引用的文件數) / 總文件數`。
    *   **修剪行動**：若 `CNR > 0.6`，`ContextHub` 必須觸發 `ContextCompactor`。實作邏輯：遍歷當前載入的 AST 節點，若該節點在最近 3 輪對話中未被提及 (`frequency == 0`)，則將其從 Context 中剔除 (Drop)，迫使模型重新聚焦。

---

## 🔍 III. X光掃描與圖譜映射 (Structural Intelligence - `forloopcodes/contextplus`)

### 5. Skeleton-First (X 光掃描) 讀取機制
*   **底層機制**：利用 **Tree-sitter** 進行 AST (抽象語法樹) 解析，僅萃取程式碼骨架。
*   **Nexus 實作細節 (D 階段)**：
    *   實作 `get_file_skeleton` 工具：解析 Python/JS 檔案，僅回傳 `class` 宣告、`def` 函數簽名、參數型別與 Docstrings。
    *   **Anti-Pattern 強制攔截**：如果 Agent 在未呼叫 `get_file_skeleton` 的情況下，試圖直接 `read_file` 超過 500 行的檔案，系統 (如 `harness_sensors`) 應直接攔截並提示：「請先閱讀骨架」。

### 6. 語義譜分群 (Spectral Clustering) 與關聯圖譜
*   **底層機制**：將專案視為圖形數據庫 (Graph Database)，節點為函數/類別，邊緣為相依關係。
*   **Nexus 實作細節 (R 階段)**：
    *   **邊緣定義 (Edge Types)**：建立 `implements`, `depends_on`, `relates_to` 關係。
    *   **影響半徑 (Blast Radius)**：當 Agent 修改了 `def login()`，`ContextHub` 必須透過圖譜查詢（例如查詢其 AST 的呼叫圖 `Call Graph`），自動抓取並注入所有標記為 `depends_on: login` 的函數骨架，確保 Agent 不會引發連鎖錯誤。
    *   **符號加載 (Symbol JIT)**：實作 `lookup_implementation(symbol_name)`，精確利用 AST 定位該符號的行數範圍（Start Line - End Line），僅擷取該區塊注入 Context。

---

## 🧠 IV. 鉤子觸發與持久化記憶 (Persistence - `thedotmack/claude-mem`)

### 7. MCP 記憶工具與 SQLite 結構
*   **底層機制**：使用輕量級關聯式資料庫持久化儲存觀察結果，並透過 MCP 工具暴露給 Agent。
*   **Nexus 實作細節 (C 階段)**：
    *   建立 `.nexus/knowledge/memory.db` (SQLite)，Schema 包含：`id`, `session_id`, `observation_type` (decision, fix, architecture), `content`, `timestamp`。
    *   提供 MCP 工具：`store_observation(type, content)` 與 `get_observations(query)`。
    *   **隱私過濾**：在寫入 DB 前，正則掃描並剔除被 `<private>` 標籤包裹的敏感資訊（如憑證、Token）。

### 8. 五大生命週期鉤子 (Lifecycle Hooks) 與自動結晶
*   **底層機制**：不在對話結束後才整理，而是在事件發生當下擷取記憶。
*   **Nexus 實作細節**：
    *   **`PostToolUse` 鉤子**：當 Agent 成功執行一次 `replace` (代碼修改) 或通過一項 Test 時，自動攔截 `stdout`，擷取修復邏輯。
    *   **`Summary` 鉤子**：在 P-X-D-R-A-C 每個 Phase 轉移時，觸發微型 LLM 調用，將該 Phase 的成果壓縮為 50 字的 `Observation` 並寫入 DB。
    *   **漸進式揭露**：新 Task 啟動 (`SessionStart`) 時，`ContextHub` 的 L1 Index 只會注入最近 5 條記憶的「標題與 ID」。

---

## 🗄️ V. 混合檢索與增量同步 (Hybrid Search - `zilliztech/claude-context`)

### 9. 混合搜尋架構 (Hybrid Search)
*   **底層機制**：結合 **BM25 + Dense Vector** 的雙軌檢索，解決精確符號名稱與語意意圖的雙重對位。
*   **Nexus 實作細節**：優化 `Palace Search` 與 `WisdomVault` 的檢索策略。在檢索時對兩個分數進行加權融合 (Rerank)，確保變數名稱拼寫與語意意圖同時命中。

### 10. 增量索引與 Merkle Tree
*   **底層機制**：基於 AST 進行智慧分塊並使用 Merkle Tree 進行增量更新。
*   **Nexus 實作細節**：在 `nexus/research/msa_indexer.py` 中引入 Merkle Tree 檔案雜湊比對。僅在檔案變動時，利用 Tree-sitter 更新 LanceDB，取代全量重掃。

---

## ⚡ VI. KV 快取優化與長文本效能 (Efficiency - `Gemma 4, DeepSeek V4, Laguna, ZAYA1`)

### 11. 跨層共享 (Shared KV) 與 逐層嵌入 (PLE)
*   **來源**：Gemma 4 (2026-04)
*   **Nexus 實作細節**：在 `Swarm` 並行修復時，優先調用具備 Shared KV 特性的模型。在 VRAM 中保留一份核心架構（如 `MUSE_PROTO`）的「常駐快取」，供所有子節點共享，將 VRAM 佔用降低 50%。利用 PLE 模型透過「查表」引入更多 Token 特有資訊。

### 12. 混合壓縮注意力 (HCA & CSA) 與 mHC
*   **來源**：DeepSeek V4 (2026-04)
*   **Nexus 實作細節**：
    *   **感知擴展**：利用 HCA (128:1 壓縮) 作為「全量代碼地圖導航器」，將專案感知範圍從數萬行擴展至百萬行級別。
    *   **穩定連通**：利用 mHC (流形約束超連接) 保證長鏈條修復軌跡 (`lineage_chain.jsonl`) 的物理穩定性，降低 `Audit` 階段的 `Trust Mismatch`。

### 13. 相位感知預算分配與遞歸聚合 (Markovian RSA)
*   **來源**：Laguna XS.2 & ZAYA1-8B (2026-05)
*   **Nexus 實作細節**：
    *   **動態預算**：重構 `context_hub.py`。**D 階段**啟用 Full Attention (128k 窗口)；**R 階段**自動調降至 Sliding Window (512 tokens)。
    *   **無限推理**：Agent 執行 `repair_loop` 時，若模型支援 RSA，則無需進行 `SessionCompaction`，直接維持完整的推理尾部與遞歸聚合狀態。

---
**[NEXUS CONTEXT ENGINEERING & EFFICIENCY ABSOLUTE SPEC v1.8 | 2026-05-17]**
**[Status: ALL granular details from 6+ projects fully preserved]**

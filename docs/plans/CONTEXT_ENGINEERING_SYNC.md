# 📚 Nexus 終極演化同步：全維度上下文工程 (Context Engineering)

> **致優化 Agent：**
> 本文件是 Nexus 上下文治理的最高實作準則。它摒棄了抽象的架構描述，直接提煉 `andrewyng/context-hub`、`davidkimai/Context-Engineering`、`forloopcodes/contextplus` 與 `thedotmack/claude-mem` 專案中的**底層機制、資料結構、API 合約與演算法細節**，並將其與 Nexus 當前的 P-X-D-R-A-C 閉環深度融合。
> **請在執行 `ContextHub` 重構或 `meta_opt` 演化時，直接將此文件作為代碼實作的 Spec。**

---

## 🏗️ I. 基礎建設與常駐治理 (Foundation - `andrewyng/context-hub`)

### 1. 依賴注入與組裝合約 (DI & Assembly Contract)
*   **底層機制**：拒絕全局變數或隨機的 API 呼叫，所有的記憶、知識與信念引擎必須透過 `ContextDependencies` 進行嚴格的建構子注入 (Constructor Injection)。
*   **Nexus 實作細節**：
    *   `ContextHub` 的 `__init__` 必須接收 `strict_deps=True`。
    *   組裝上下文時，必須執行**預算分配 (Budget Allocation)**。例如：總 Token 預算 128k，`L0/L1` 保留 2k，`History` 保留 10k，剩餘才分配給 `Research` 與 `Code`。
    *   必須實作精確的 Token 預測函式（例如：程式碼每 3.5 個字元約 1 Token），在裝載前進行 `estimated_total > threshold` 校驗。

### 2. L0/L1 常駐記憶的物理隔離
*   **底層機制**：將系統提示詞 (System Prompt) 劃分為不可變的物理防線。
*   **Nexus 實作細節**：
    *   **L0 結構**：硬編碼 `[BOUNDARIES: core, metrics] [PROHIBITED: delete-history, skip-verify]`。
    *   **L1 結構**：從 `.nexus/state/last_handoff.json` 讀取並注入 `[TASK: {id}] [PHASE: {phase}] [TOKEN: {token}]`，強制維持跨回合的狀態對齊。

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
*   **底層機制**：利用 **Tree-sitter** 進行 AST (抽象語法樹) 解析，僅萃取程式碼的骨架，不包含具體實作。
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
    *   **`Summary` 鉤子**：在 P-X-D-R-A-C 每個 Phase 轉移時（如從 R 進入 A），觸發微型 LLM 調用，將該 Phase 的成果壓縮為 50 字的 `Observation` 並寫入 DB。
    *   **漸進式揭露**：新 Task 啟動 (`SessionStart`) 時，`ContextHub` 的 L1 Index 只會注入最近 5 條記憶的「標題與 ID」，如 `[MEM-102: Auth Session Timeout Fix]`。若 Agent 需要細節，必須主動調用 `get_observations("MEM-102")`。

---
**[NEXUS CONTEXT ENGINEERING UNIFIED SPEC v1.5 | 2026-05-17]**
**[Status: DEEP MECHANICS & CODE-LEVEL MAPPING ENFORCED]**

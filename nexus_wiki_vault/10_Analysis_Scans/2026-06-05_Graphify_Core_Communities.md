# 物理模組映射圖 (Empirical Architecture Map - Graphify)

**掃描日期**: 2026-06-05
**工具來源**: `graphify` (基於 AST 靜態分析，154,890 節點，247,725 邊界)
**原始產物位置**: `docs/perplexity/graphify/`

本報告提煉自 codebase 的實體依賴關係，反映了程式碼「實際上的分佈」，而非設計文件的理想。

## 五大核心社區 (Top 5 Communities)

### 1. 專案治理與除錯追蹤 (Community 7)
*   **規模**：547 個節點（規模最大）。
*   **核心內容**：主要集中在 Nexus 引擎的「治理防護」與「歷史錯誤追蹤」。
*   **涵蓋節點範例**：
    *   `2026-04-13: AutoResearch Control Plane Integration confuses file paths`
    *   `2026-04-14: NightShift high-confidence landing still requires global contract verification`
    *   `2026-04-18: v25 Governance Gate FAIL (Incomplete Hardening)`
*   **架構洞察**：這是整個專案的**大腦記憶庫**與防呆邊界，記錄了大量 ADR、決策失敗的教訓（Learning Closure）與 Gate 攔截規則。

### 2. 核心建模與參數驗證 (Community 2 & 6)
*   **規模**：445 節點 + 457 節點。
*   **核心內容**：處理核心資料結構的屬性設定、邊界限制（bounding_box）、參數驗證機制（validation）。
*   **涵蓋節點範例**：
    *   `Parameter.fvalidate`
    *   `Decorator to register a new kind of validator function`
    *   `Model specific post evaluation processing of outputs`
*   **架構洞察**：這部分代碼負責確保傳入 Nexus / 代理引擎的參數與狀態矩陣是合法且互不衝突的（mutually broad）。

### 3. UI 雜訊清理與標準化摘要 (Community 11)
*   **規模**：188 節點。
*   **核心內容**：專案中的解析、提煉與格式化邏輯。
*   **涵蓋節點範例**：
    *   `clean_noise()` / `parse_evolution_log()`
    *   `產出判斷｜影響｜建議的標準化駕駛艙摘要`
*   **架構洞察**：這是典型的 **Data Refinery（資料精煉）** 模組，負責將龐雜的執行日誌或非結構化文字，壓縮成供 Agent 或 Dashboard 閱讀的乾淨 Context。

### 4. 陣列與位元底層操作 (Community 8)
*   **規模**：255 個節點。
*   **核心內容**：處理低階資料型態轉換與序列化。
*   **涵蓋節點範例**：`_all_matching_dtype()`, `bitarray_to_bool()`, `BitArray`
*   **架構洞察**：這通常與 Embedding 處理、圖譜節點的高效儲存（如 LanceDB 相關）或記憶體狀態序列化相關。

### 5. 時間系統與狀態檢查 (Community 9)
*   **規模**：316 個節點。
*   **核心內容**：處理時間增量、狀態衰退與警告機制。
*   **涵蓋節點範例**：`_LeapSecondsCheck`, `TimeDeltaInfo`, `AstropyDeprecationWarning`
*   **架構洞察**：這與 Agent 的 **Memory Decay（記憶衰退）**、Stale Link 修剪或排程任務的時間戳對齊高度相關。
# 深化建議：儲存與搜尋職責解耦重構規格 (v25.5)

## 1. 目標
修復 Nexus 基礎設施層的層級依賴錯誤，確保儲存實作的純粹性與可更換性。

## 2. 重構要點

### 2.1 介面拆分 [PARTIAL]
*   **`MemoryStorage`** (Infrastructure) [DONE]: 僅包含 `put`, `get`, `delete`, `list` 等原子操作。
*   **`SemanticSearcher`** (Service/Bridge) [PENDING]: 負責將 `MemoryStorage` 的資料建立索引並提供語義搜尋能力。

### 2.2 移除違規導入 [CRITICAL PENDING]
*   徹底移除 `storage_implementations.py` 中對 `nexus.services.*` 的任何導入。
*   搜尋邏輯應由 `MemoryService` 在更高層級進行組合調用。

### 2.3 強化租戶隔離 [PARTIAL]
*   在 `MemoryStorage` 層級實作 `scoped_access(tenant_id)`，確保檢索操作被嚴格限制在特定路徑下。

## 3. 預期效益
*   **解耦**：基礎設施層不再受高層業務邏輯變動影響。
*   **靈活性**：可輕鬆實作 `S3Storage`, `SqliteStorage` 等不同後端而不必擔心搜尋邏輯的移植問題。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*

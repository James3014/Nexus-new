# Nexus 基礎設施與服務層架構診斷報告 (v25.5)

## 1. 核心問題診斷

### 1.1 循環依賴 (Circular Dependency)
*   `nexus/infrastructure/storage_implementations.py` 內部導入了高層的 `nexus/services/memory_repository.py`。
*   後果：基礎設施層（低層）依賴於服務層（高層），違反了乾淨架構原則，導致模組難以獨立測試與更換。

### 1.2 抽象洩露與隔離不全
*   儲存實作中，多租戶隔離 (Multi-tenancy) 邏輯僅停留在目錄層級，且檢索邏輯 (`retrieve`) 會跨租戶掃描。
*   後果：基礎設施層未能提供強力的隔離保證，增加了資料洩漏的風險。

### 1.3 靜態類型缺失 (Static Typing Gap)
*   系統過度依賴動態加載的 JSON Schema，而非強類型的 Python 對象。
*   後果：執行時錯誤率高，且 AI 在輔助開發時缺乏類型提示。

## 2. 改進建議

### 建議一：儲存與搜尋職責解耦 (Storage/Search Decoupling)
*   **目標**：修復基礎設施層的循環依賴。
*   **方案**：`MemoryStorage` 僅保留 CRUD 功能；搜尋與語義檢索應透過獨立的 `SearchProvider` 接口實現。

### 建議二：導入強類型資料契約 (Typed Data Contracts)
*   **目標**：提升資料傳輸的可靠性。
*   **方案**：將 `nexus/schemas/` 轉化為 `nexus/contracts/` 下的 Pydantic 或 Dataclasses 模型。

### 建議三：建立韌性鎖定機制 (Resilient DistLock)
*   **目標**：增強系統在極端環境下的生存能力。
*   **方案**：當 Redis 基礎設施不可用時，`DistLock` 應能自動降級為本地檔案協調鎖。

## 3. 實作進度 (v25.5 Update)

### [部分完成] 建議一：儲存與搜尋職責解耦
*   **進度**：已定義 `MemoryStorage` 協議與租戶目錄化。
*   **問題**：`LanceDBStorage` 仍存在對 `nexus.services` 的違規導入，尚未完全解耦。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*

# 深化建議：ContextHub 提供者模式重構規格 (v25.5)

## 1. 目標
將 `ContextHub` 從「主動管理者」轉變為「被動組裝器」，透過明確的依賴注入（DI）提升模組的可測試性與局部性。

## 2. 重構要點

### 2.1 移除主動導入 (Lazy Imports)
*   移除 `__init__` 中對 `WisdomVault`, `BeliefEngine`, `KnowledgeInjector` 的 `try-import` 邏輯。

### 2.2 定義注入接口
*   定義 `ContextDependencies` 資料類別或 Protocol。
*   `ContextHub` 應接收這些預先實例化好的對象，而非自行建立。

### 2.3 分離決策邏輯 (Pre-routing)
*   `make_pre_routing_decision` 應改為接受一個 `StateView` 對象，而非在內部調用 `state_io.load_global_state()`。

## 3. 實作範例 (偽代碼)
```python
# 重構後
class ContextHub:
    def __init__(self, deps: ContextDependencies):
        self.belief_engine = deps.belief_engine
        self.wisdom_vault = deps.wisdom_vault
        # ... 僅進行賦值，不進行探測
```

## 4. 預期效益
*   **隔離性**：可單獨測試 `ContextHub` 的壓縮算法，無需建立真實的資料庫或檔案系統。
*   **透明性**：系統組件間的依賴關係一目瞭然，避免隱藏的啟動錯誤。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*

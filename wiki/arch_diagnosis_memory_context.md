# Nexus 記憶與上下文管理系統架構診斷報告 (v25.5)

## 1. 核心問題診斷

### 1.1 層級依賴倒置 (Layer Inversion)
*   `nexus/core/mem_palace.py` 繼承自 `nexus.services.mem_palace`。這違反了「核心不依賴服務」的原則。
*   後果：當 Service 層變動時，Core 核心邏輯會受到非預期的影響。

### 1.2 初始化地獄 (Injection Hell)
*   `ContextHub` 在建構時主動嘗試導入並實例化幾乎所有核心組件 (`WisdomVault`, `BeliefEngine` 等)。
*   後果：模組局部性 (Locality) 極差，測試與除錯難度極高，且隱藏了組件間的循環依賴風險。

### 1.3 職責混雜 (Mixed Responsibilities)
*   `MemoryCoordinator` 同時處理低階檔案鎖定 (fcntl) 與高階貝式反壓 (Backpressure) 計算。
*   後果：模組「深度」不足，內部邏輯過於「發散」。

## 2. 改進建議

### 建議一：導入提供者模式 (Provider Pattern)
*   **目標**：消除 `ContextHub` 內部的自動導入與強耦合。
*   **方案**：由外部注入 `BeliefProvider` 與 `MemoryProvider`。

### 建議二：解耦鎖定策略與機制
*   **目標**：將 `MemoryCoordinator` 的機制與策略分離。
*   **方案**：鎖定機制僅負責原子操作，動態頻率調整（Nerve Threshold）應透過策略接口傳入。

### 建議三：定義核心記憶契約 (Memory Contract)
*   **目標**：修正 `MemoryPalace` 的繼承關係。
*   **方案**：在 Core 定義 `MemoryVault` 協議，Service 則負責實作該協議。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*

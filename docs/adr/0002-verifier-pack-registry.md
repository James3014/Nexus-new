# ADR 0002: 基於註冊制的 Verifier Packs 插件化

## 狀態
已接受 (Accepted)

## 背景
領域驗證器 (如 Django 語義檢查) 具有高度的 Domain-Specific 特性。若將所有驗證器直接硬編碼在 `CommitteeController` 中，會導致代碼膨脹，且難以支持新題庫 (如 Astropy vs Django) 的按需載入。

## 決策
實施 `Verifier Packs` 機制：
1. **Pack 封裝**: 將相關的驗證器封裝成 `AstropyPack`、`DjangoPack`。
2. **領域標籤**: 每個 Pack 具備 `domain_tags`屬性。
3. **註冊中心**: `PackRegistry` 根據當前任務的領域標籤，動態啟用對應的外掛包。

## 後果
- **優點**: 
  - 核心治理邏輯 (Selection Policy) 與領域知識徹底解耦。
  - 支持「物理插件」式的能力擴展，不改動主線代碼。
  - 符合 Open-Closed Principle (OCP)。
- **缺點**: 
  - 執行時需要一次 Registry 尋找開銷 (可忽略不計)。

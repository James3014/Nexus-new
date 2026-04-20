# 🧱 Unified Service Registry & Mesh
**[PHYSICAL_STATUS: REGISTRY_ACTIVE | MIGRATION_PENDING]**

## 1. 統一服務註冊中心
`ServiceRegistry` 是 Nexus 內部組件的唯一註冊與發現入口，解決重複實例化問題。

## ⚙️ 實體化註冊規約
- **單例模式 (Singleton)**: 全系統僅存一份 `nexus_service_registry`。
- **註冊機制**:
    - **強型別**: 必須提供 Service 的 `Type` 與 `Instance`。
    - **狀態**: 追蹤 `INIT`, `ACTIVE`, `STOPPED` 生命週期。
- **發現機制**:
    - 透過 `registry.get_service("name")` 安全獲取實例。
    - **物理位置**: `nexus/services/registry.py`。

## 2. 服務治理路徑
- **SSoT**: 所有核心 Service（如 `MemoryRepository`, `SkillsRouter`）應強制註冊。
- **解耦**: 透過 Registry 獲取依賴，取代模組內部的動態 `import`。

## 🚧 待完成優化
- **全量接管**: 目前僅有核心組件完成註冊，剩餘 80+ 檔案需逐步併入 Mesh。

---
**[Source: Truth Realignment Audit Stage 8 - 2026-04-20]**

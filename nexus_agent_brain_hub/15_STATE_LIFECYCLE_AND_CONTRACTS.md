# 🔄 State Lifecycle & Contracts

## 1. 狀態生命週期 (State Lifecycle)
Nexus 透過嚴格的狀態監控，確保系統從初始化到結案的每一步都是可追溯的。

## 2. 狀態遷移路徑
- **`INIT`**: 環境預檢 (Preflight) 與 CLI 對齊。
- **`STAGING`**: 建立影子環境或隔離 Worktree。
- **`TRANSITION`**: 執行實體修改，狀態暫存於 `Metabolism`。
- **`VERIFYING`**: 進入 Gate 鏈路（Linter -> Test -> HI Check）。
- **`COMMITTED`**: 通過 C 階段，狀態固化並封印 (Sealed)。

## 3. Pydantic 契約約束
- **嚴格型別**: 核心數據結構（如 `MemoryCandidate`, `RoutingResult`）均使用 Pydantic BaseModel。
- **Runtime Validation**: 禁止任何未定義欄位的注入 (`extra='forbid'`)，確保 API 契約的長期穩定。

## 4. 快照機制 (Snapshotting)
- 在執行高風險任務前，系統自動產出 `state_snapshot.json`。
- 若任務中斷，可透過 `nexus resume` 從快照點精準恢復。

---
**[Source: nexus_wiki_vault/04_State/State - Lifecycle.md]**

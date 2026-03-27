# Skills Router 遷移說明（2026-03-28）

## 目前主路徑
- 正式路由器：`nexus/core/router.py`

## 舊路徑狀態
- `scripts/core/skills_router.py` 已改為 **deprecated shim**。
- 作用：只保留舊 import 相容，不再作為主實作維護。

## 開發準則
1. 新增或修改技能路由邏輯，只改 `nexus/core/router.py`。
2. `scripts/core/skills_router.py` 不再新增功能。
3. 若未來確認無舊引用，可直接刪除 shim。


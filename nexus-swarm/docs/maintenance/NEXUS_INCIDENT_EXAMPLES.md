# NEXUS_INCIDENT_EXAMPLES

## 案例 1: 任務恢復風暴 (Recovery Storm)
- **現象**: 大量 `task.recovered` 事件噴發，TPS 降低。
- **原因**: Node 執行逾時導致租約被 Manager 重收。
- **措施**: 增加 `LeaseDuration` 或擴展 Node 運算資源。

## 案例 2: 安全邊界拒絕 (SECURITY_VIO)
- **現象**: 稽核報告顯示 `status: SECURITY_VIO`。
- **原因**: 任務試圖寫入非白名單目錄。
- **措施**: 更新 `NEXUS_ALLOWED_PATHS`。

# NEXUS_MAINTENANCE_GUARDRAILS

## ⛔️ 禁止改動內容 (Forbidden Changes)
1. **禁止在 Actor 循環外寫入狀態**：`persistence.go` 的數據變更必須透過 Actor Channel。
2. **禁止破壞 NSP 協定之 W3C Trace 傳遞**：失去 Traceability 等於失去治理權。
3. **禁止移除 Fail-Open (Default PASS) 邏輯**：在治理平面成熟前，絕不允許卡住下游。

## ⚠️ 高風險操作
- **DB 模型重定義**：涉及歷史數據遷徙與租約恢復邏輯。
- **Region 矩陣變更**：會影響分散式調度的負載均衡演算法。

## 修復建議
在執行任何功能性異動前，請確保先在 `shadow_audit_v24.sh` 環境中測試。

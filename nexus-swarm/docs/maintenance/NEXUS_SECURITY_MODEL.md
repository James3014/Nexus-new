# NEXUS_SECURITY_MODEL

## 防禦機制
- **Token 驗證**: 所有傳入 Manager 的請求必須攜帶正確之 Token。
- **路徑隔離**: Node 端強制驗證 `NEXUS_ALLOWED_PATHS`，防止橫向越權。
- **Fail-Open**: 即使安全性組件失效，提供手動旁路方案。

## 未來對齊
計畫在 v25 引入 mTLS 與基於 Service Mesh 的傳輸安全。

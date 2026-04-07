# 💳 Nexus v25.0 REVENUE_ENGINE_SPEC

## 🎯 商業邏輯概要
Nexus Swarm 自 v25.0 起，轉型為 **SaaS 商業化智能架構**。所有 API 調用受 `BillingEngine` 管控。

## 🛡️ 關鍵契約 (Critical Contracts)

### 1. 支付檢核 (Payment Verification)
- **Oracle**: `nexus/services/billing_engine.py` (Stripe Native)。
- **邏輯**: 每次 `memory_route` 請求前，必須執行 `billing.get_subscription_status(tenant_id)`。
- **行為**: 狀態非 `active` 則返回 `STATUS_BLOCKED`。

### 2. 租戶分級 (Tiering)
- **Starter**: 限額 10,000 查詢/月。
- **Pro**: 無限查詢，優先分配 US-West/EU-Central 高性能節點。

### 3. 數據主權 (Data Sovereignty)
- **Export**: 支援 GDPR `tenant-export`。
- **Delete**: 支援 `tenant-delete` (物理抹除分片)。

## 🏁 最終門檻 (Commercial Gates)
- **MRR**: 必須可追蹤。
- **Throughput**: 100 租戶併發下 P95 < 20ms。

---
**[DOCUMENTED BY NEXUS v25.0 | v25.0.3.751.0]**

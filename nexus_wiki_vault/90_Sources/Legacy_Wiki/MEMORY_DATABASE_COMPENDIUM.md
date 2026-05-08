# 🧠 Nexus v25.5 記憶與資料庫核心架構全書 (Compendium)

## 🏛️ 1. 物理層：多租戶隔離分片 (Physical Sharding)
- **存儲路徑**: `.nexus/tenants/{tenant_id}/`
- **資料表**:
  - **Vector**: `lancedb/` (語義檢索)
  - **Relational**: `palace.sqlite` (元數據與 Episode 追蹤)
- **硬體監控**: `TenantIOPSMonitor` 確保 P50 < 1000ms。

## 🏰 2. 核心引擎：MemPalace 深度整合
- **嵌入模式**: Git Submodule `nexus-mempalace`。
- **召回層級**: Palace (租戶) > Wing (象限) > Room (房間)。
- **調用模式**: gRPC `MCPDelegator` 原子化調用，Token 消耗 < 145。

## 🔄 3. 智慧閉環：Session 代謝 (Metabolism)
- **觸發閾值**: 85% Token 使用率。
- **精華提取**: 自動將 Manifest/Lineage/Progress 備份至 Arweave。
- **無損接力**: 生成 `Golden Source` TX ID，實現長對話 context 永生。

## 🛡️ 4. 治理層：智慧裁判與去重
- **壓縮協議**: **AAAK 30x**，對語義重複數據進行消冗。
- **防火牆攔截**: `DomainFirewall` 基於 187 個技能領地過濾檢索結果。
- **計費聯動**: 欠費租戶將被物理阻斷資料庫存取權限。

---
**[DOCUMENTED BY NEXUS v25.5 | v25.5.3.809.0]**

# 🧱 Unified Service Registry & Mesh (v32.7)
**[PHYSICAL_STATUS: MESH_ENFORCED | SERVICE_ISOLATION]**

## 1. 服務網格與組件治理
Nexus 已將核心「單體引擎」拆解為基於 **Service Mesh (服務網格)** 的細粒度架構。這實現了開發與治理功能的物理級解耦。

## ⚙️ 實體組件登記冊 (Engine Registry)
所有的關鍵邏輯現已收斂至專屬服務：

| Domain | Key Service | Role |
| :--- | :--- | :--- |
| **Execution** | `RepairLoopService` | 管理補丁生成與驗證的原子循環。 |
| **Governance**| `ForecastGateService` | 在 Phase P 預判任務合規性。 |
| **Recall** | `AutonomicRoutingService`| 執行 MSA 與環境感知的技能路由。 |
| **Telemetry** | `SignalQueueService` | 處理跨進程的非同步事件通訊。 |
| **Learning** | `BenchmarkService` | 提供 A/B 數據閉環的性能對標。 |

## 2. 物理實體 (Today's Decoupled Alignment)
- **Bootstrap Factory**: `nexus/engine/bootstrap.py`。
- **Mesh Registry**: `nexus/services/registry.py`。
- **Service Root**: `nexus/engine/`, `nexus/research/learn/`。

---
**[Source: April 21 Service Extraction | REFACTOR_SYNCED]**

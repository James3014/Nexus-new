# 🧠 Core Orchestrator & Coordinator
**[PHYSICAL_STATUS: PRODUCTION | STATE_LOCKING_ACTIVE]**

## 1. 核心指揮邏輯
`Coordinator` 是 Nexus 的中樞神經，負責維持 `Supreme Master Loop` 的狀態一致性與跨階段調度。

## 2. 實體職能
- **狀態管理**: 透過 `NexusState` (Pydantic) 監控全專案物理健康。
- **任務分發**: 調度 `CampaignGeneral` 進行任務 DAG 生成。
- **並發防護**: 透過 `threading.RLock` (可重入鎖) 確保事件廣播與狀態更新的原子性，消滅死鎖。
- **狀態修剪**: `StateRepository` 自動執行歷史 Tail-Cut (100 條上限)，防止磁碟赤字。

## 3. 核心組件
- **`Coordinator`**: 協調 P/X/D/R/A/C。
- **`AutonomicRouter`**: 自動感應任務難度，決定路由策略。
- **`ProjectPlanner`**: 接收 `StrategicEnvelope` 並生成計畫。

## 4. 關鍵契約
- **Fail-Closed**: 當遠端服務（如 LLM API）異常時，自動降級至 `Local Bonsai Brain`，絕不憑空幻覺。

---
**[Source: nexus_wiki_vault/02_Modules/Module - Core Orchestrator.md]**

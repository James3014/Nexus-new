# 🧠 Core Orchestrator & Coordinator

## 1. 核心智慧邏輯 (Intelligence Logic)
`Coordinator` 是 Nexus 的中樞神經，負責維持 `Supreme Master Loop` 的狀態一致性。

## 2. 主要職能 (Responsibilities)
- **狀態管理**: 透過 `NexusState` 監控全專案的物理健康度。
- **任務分發**: 調度 `CampaignGeneral` 進行任務 DAG 的生成。
- **環境屏障**: 在 `Hyper/NightShift` 模式下，實施嚴格的 `File Freeze` 邊界。

## 3. 核心類別設計
- **`Coordinator`**: 主入口，協調 P/X/D/R/A/C。
- **`AutonomicRouter`**: 自動感應任務難度，決定路由策略。
- **`ProjectPlanner`**: 接收戰略封套 (StrategicEnvelope)，生成細粒度計畫。

## 4. 關鍵契約 (Contracts)
- **In-process Protection**: 嚴禁在未獲取 `Lock` 的情況下修改全域狀態。
- **Graceful Degradation**: 當遠端服務（如 OpenAI/Gemini API）異常時，自動降級至 `Local Bonsai Brain`。

---
**[Source: nexus_wiki_vault/02_Modules/Module - Core Orchestrator.md]**

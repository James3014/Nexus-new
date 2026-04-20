# 📡 Fleet Command & Swarm Adapters
**[PHYSICAL_STATUS: INFRA_WIRED | CROSS_NODE_CAPABLE]**

## 1. 實體化機群基礎設施
Nexus 透過「機群指揮系統」實現多個 Agent 在不同沙盒環境中的並行與跨機協作。

## ⚙️ 實體化協調規約
- **環境隔離**: 每個 Drone 運作在獨立的 `.nexus-swarm-NNN` 目錄。
- **通信安全 (mTLS)**: 只有具備有效證書（位於 `.nexus/certs`）的節點才能參與 Swarm。
- **跨機記憶同步 (Redis)**: 透過 `nexus/services/memory.py` 同步 `lesson_writeback` 與熱點快照。
- **Locking Service**: 目前具備基於 Redis 的單點鎖，分散式共識鎖 (Raft) 尚在優化路徑中。

## 2. 分散式任務分發
- **動態分派**: `CampaignGeneral` 根據負載，將 DAG 任務掛載至閒置 Drone。
- **中斷恢復**: Drone 崩潰後，系統自動從最近的 Checkpoint 恢復。

## 🚧 待完成優化
- **全域 Barrier**: 跨物理機的同步屏障目前仍由 `asyncio` 在本地端模擬。

---
**[Source: nexus_wiki_vault/02_Modules/Fleet Command System.md]**

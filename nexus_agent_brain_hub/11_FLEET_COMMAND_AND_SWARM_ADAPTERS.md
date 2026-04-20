# 📡 Fleet Command & Swarm Adapters

## 1. 多 Agent 協作 (Swarm Intelligence)
Nexus 透過「機群指揮系統 (Fleet Command)」實現多個 Agent 在不同沙盒環境中的並行作業。

## 2. Swarm Adapter 機制
- **環境隔離**: 每個 Drone 運作在獨立的 `.nexus-swarm-NNN` 目錄中，具備完整的虛擬環境。
- **狀態同步**: 透過 `Metabolism Engine` 實現不同沙盒間的增量同步，解決物理路徑差異。
- **Locking Service**: 使用分散式 PID Lock 防止多個 Agent 競爭同一個寫入路徑。

## 3. 分散式任務分發
- **動態分派**: `CampaignGeneral` 根據當前資源負載，動態將 DAG 任務掛載至閒置的 Drone。
- **中斷恢復**: 若單一 Drone 崩潰，系統自動重啟並從最近的 Checkpoint 恢復。

## 4. 屏障規約 (Barrier Protocol)
- 只有當同一層級的所有任務均通過 `Audit` 後，系統才允許進入下一階段的同步 (Barrier Sync)。

---
**[Source: nexus_wiki_vault/02_Modules/Fleet Command System.md]**

# 深化建議：自癒協定化與安全解耦規格 (v25.5)

## 1. 目標
將 Nexus 從「單機戰甲」演進為「分散式蜂群」，確保自癒建議的可傳輸性與通訊的安全靈活性。

## 2. 重構要點

### 2.1 定義 `HealingArtifact` (自癒契約)
*   不再回傳 `List[Dict]`，而是建立一個包含 `diagnosis_hash`, `repair_ops`, `validation_commands` 的不可變物件。
*   支持序列化為 JSON/Protobuf，以便透過 EventBus 分發。

### 2.2 實作傳輸處理器模式 (Transport Processor)
*   重構 `SecureRegistrySync`，使其接受一個 `IncomingMessageHandler` 回調。
*   所有關於 `SkillFrontmatter` 的業務邏輯移出安全模組。

### 2.3 信心指標掛載 (Belief Tracing)
*   在 `NexusTracer` 中新增 `record_belief_shift(task_id, old_val, new_val)`。
*   自動將信心變動標記為 Span Event 或計量指標。

## 3. 預期效益
*   **集群能力**：節點 A 診斷，節點 B 執行，實現真正的分佈式自癒。
*   **強大監測**：開發者可透過 Grafana 觀察整個 Swarm 集群的「整體信心波動圖」。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*

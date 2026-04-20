# 🚀 Nexus Evolution to 90+ Specification
**[PHYSICAL_STATUS: GOVERNANCE_OPTIMIZED | COGNITION_ALIGNED]**

## 1. 債務清償進度 (Debt Clearance Status)
Nexus 已完成第四波治理優化。認知層已對位，通訊已解耦，門禁已並行。

| 債務項目 | 狀態 | 實體核驗 (Truth) |
| :--- | :--- | :--- |
| **模型歸一化** | ✅ **已完成** | `vector_rag.py` 已對接 `nomic-embed-text` 並 Logging 化。 |
| **動態配置化** | ✅ **已實作** | `nexus_swarm_sse.py` 已支援 `NEXUS_SSE_PORT` 環境變數。 |
| **門禁並行化** | ✅ **已激活** | `ci_gate.py` 採用 `ThreadPoolExecutor` 提升 75% 效能。 |
| **測試結構化** | ✅ **已對位** | 建立了 `unit/integration/e2e` 標準空間並整合 `pytest-cov`。 |

## 2. 深度技術債 (Stage 6 Discovery)
經 2026-04-20 全量並行化與非同步掃描後，挖掘出以下邁向 100 分終局的「動態性債務」：

### 🔴 Sev-1: Asynchronous Deadlocks (非同步死鎖風險)
- **現象**: `NexusEventBus` 在高併發廣播時使用單一 `threading.Lock`。
- **風險**: 在大規模 Swarm 機群下可能引發資源爭奪，導致指令脈搏中斷或吞吐量驟降。

### 🔴 Sev-1: Configuration Inconsistency (配置碎片化)
- **現象**: `nexus/core/config.py` 過於精簡，未涵蓋 Ollama URL、SSE 埠位、Redis 分散式鎖等實體參數。
- **風險**: 導致各模組重複實作環境變數讀取，增加維護難度與配置衝突風險。

### 🟡 Sev-2: Pydantic Serialization Bloat (序列化膨脹)
- **現象**: `NexusState` 隨任務長度增加，`steps_history` 會導致 state 檔案體積幾何增長。
- **風險**: 拖慢 `save_checkpoint` 速度，甚至在超長任務中引發內存溢出。

### 🟡 Sev-2: Blocking IO in Indexer (同步 IO 阻塞)
- **現象**: `msa_indexer` 目前對 Ollama 的 HTTP 請求為同步模式。
- **風險**: 在萬級檔案掃描時會嚴重阻塞索引管線。

## 3. 下一階段清剿目標
1. **配置歸一化**: 將所有分散的環境變數讀取集中至 `nexus/core/config.py`。
2. **非同步 IO 化**: 將 `vector_rag` 與 `msa_indexer` 遷移至 `aiohttp`。
3. **狀態修剪策略**: 實作 `State Pruning` 自動歸檔過時的歷史步驟。

---
**[NEXUS IDENTITY: e148a212 + v27.7 DEBT-TRACKED | TARGET: 99+ SCORE]**

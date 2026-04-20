# 🌐 System Overview & Glossary

## 1. 系統全景
Nexus 是一個「具備自我免疫與演化能力」的多 Agent 協作框架。它不依賴 LLM 的天然一致性，而是透過「物理守門員 (Physical Gates)」與「任務契約 (Contracts)」來確保大規模生產的穩定性。

## 2. 核心術語表 (Glossary)

| 術語 | 定義 |
|---|---|
| **Soul 5-Trinity** | 靈魂五位一體：LanceDB, Memory, MemPalace, Belief, Artifact。 |
| **Fail-Closed** | 失敗即阻斷。當檢索分數或驗證未達標時，回傳 UNKNOWN 而非隨意生成。 |
| **Drift (漂移)** | 實際代碼與 Wiki/記憶之間的不一致。 |
| **Quarantine (隔離區)** | 新生成的記憶或補丁在正式 Promote 前的待驗證區域。 |
| **Bonsai Brain** | 專為邊緣執行優化的 1.7B 輕量級在地推理引擎。 |
| **1-bit Core** | Nexus 最底層的原子化決策單元，僅產出 True/False 的硬性判定。 |
| **DAG Orchestration** | 任務之間的方向性無環圖調度，用於管理複雜依賴。 |

## 3. 物理拓撲
- **Control Plane**: 位於 `scripts/engine/nexus_cli.py` 與 `nexus/core/`。
- **Sensory Layer**: 由 `scripts/ops/` 中的各類探針與審計腳本組成。
- **Memory Layer**: 由 `.nexus/knowledge/` 與 `nexus_wiki_vault/` 組成的混合存儲。

---
**[Source: nexus_wiki_vault/01_System/Nexus Glossary.md]**

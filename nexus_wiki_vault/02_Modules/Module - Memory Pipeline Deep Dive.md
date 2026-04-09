---
aliases:
- Memory Deep Dive
- RAG Pipeline
- Knowledge Flow
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[Module - Intelligence and Context Core](Module - Intelligence and Context Core.md)'
- '[Module - Implementation Responsibility
  Matrix](Module - Implementation Responsibility Matrix.md)'
- '[Module - Skill Memory Closed Loop](Module - Skill Memory Closed Loop.md)'
source_of_truth: nexus/services/memory.py
status: active
tags:
- services
- memory
- rag
- lance
- dive
title: Module - Memory Pipeline Deep Dive
type: module
version_scope:
- v22
- v23
---



# Module - Memory Pipeline Deep Dive

## One-sentence summary
本頁深入解析 Nexus 的長期記憶管道、[LanceDB](Module - Memory Repository.md) 整合細節與基於 Episode 的知識檢索流程。 [Source: nexus/services/memory.py]

## Role / responsibility
- **記憶存取控制**: 管理向量庫與物理文件系統間的數據交換。
- **語義召回 (RAG)**: 提供高性能的 Embedding 檢索引腳。
- **知識歸檔**: 負責將短期任務數據沉澱為長效治理資本。

## Memory Three Systems (記憶三系統)

Nexus v23 採用階層式三系統架構來管理知識與智慧：

| System | Role (角色) | Strategy (策略) |
|---|---|---|
| **MemPalace** | **魂/邏輯引擎 (Soul/Logic)** | 處理信念修正 (Belief Revision)、靈魂對齊與高階決策邏輯。 |
| **Metabolism (AutoDream)** | **智/壓縮引擎 (Distillation)** | 會話新陳代謝引擎。透過自動夢境將繁雜的對話日誌與錯誤提煉成 `session_seed.json`，避免幻覺與 Token 崩潰。 |
| **LanceDB** | **積/向量引擎 (Wisdom/Vector)** | 儲存經過結晶的代碼模式 (Patterns) 與智慧教訓 (Lessons)，驅動召回。 |
| **Memory** | **基/文件系統 (Base/RAG)** | 處理原始文件、GitHub 存儲與基本 RAG 檢索。 |

## Memory Component Registry (記憶組件詳解)

| Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **MemPalace** | 處理 Belief Revision 與智慧節點連通。 | [Source: nexus/services/mem_palace.py] |
| **LanceDB** | 提供高效向量檢索與智慧過濾。 | [Source: nexus-swarm/wisdom/wisdom_memory] |
| **Memory Service** | 傳統 RAG 管道與服務適配。 | [Source: nexus/services/memory.py] |

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 記憶系統導航。
- **[Module - Intelligence and Context Core](Module - Intelligence and Context Core.md)**: 提供查詢意圖與上下文包。

## Downstream
- **[Module - Implementation Responsibility Matrix](Module - Implementation Responsibility Matrix.md)**: 記憶模組與物理檔案映射.
- **[Module - Skill Memory Closed Loop](Module - Skill Memory Closed Loop.md)**: 三系統閉環資料流與技能選取整合 (Phase 13).
- **[[Ops - CI/CD Promotion Gate]]**: 記憶完整性作為發版審計標誌。

## Related modules / files
- `nexus/services/mem_palace.py`: 靈魂殿堂引擎。 [Code: nexus/services/mem_palace.py]
- `nexus/services/memory.py`: 記憶服務。 [Code: nexus/services/memory.py]

## Source notes
- v22 Engine Spec: 要求長效記憶的召回延遲 (90th percentile) 不得超過 800ms。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [x] **Memory Tiering**: 已於 v23 透過「三系統架構」(MemPalace/LanceDB/Memory) 完成實體化。
- [x] **Memory-Skill Integration**: 已於 Phase 13 透過 `ContextHub._recommend_skills()` 與 `SkillRegistry.search_by_affinity()` 完成閉環。詳見 [Module - Skill Memory Closed Loop](Module - Skill Memory Closed Loop.md)。

---
Back to [System Overview](../00_Home/System Overview.md)

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]
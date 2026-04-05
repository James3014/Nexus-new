---
title: Module - Memory Pipeline Deep Dive
aliases: [Memory Deep Dive, RAG Pipeline, Knowledge Flow]
type: module
status: active
version_scope: [v22, v23]
source_of_truth: nexus/services/memory.py
related_pages:
  - "[[Module - Intelligence and Context Core]]"
  - "[[Module - Implementation Responsibility Matrix]]"
tags: [services, memory, rag, lance, dive]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Module - Memory Pipeline Deep Dive

## One-sentence summary
本頁深入解析 Nexus 的長期記憶管道、LanceDB 整合細節與基於 Episode 的知識檢索流程。 [Source: nexus/services/memory.py]

## Role / responsibility
- **記憶存取控制**: 管理向量庫與物理文件系統間的數據交換。
- **語義召回 (RAG)**: 提供高性能的 Embedding 檢索引腳。
- **知識歸檔**: 負責將短期任務數據沉澱為長效治理資本。

## Memory Component Registry (記憶組件詳解)

| Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Memory Service** | 記憶管道的主入口與服務適配。 | [Source: nexus/services/memory.py] |
| **Memory Repository** | 實體 LanceDB 表與磁碟 IO 管理。 | [Source: nexus/services/memory_repository.py] |
| **Memory Indexer** | 高效率向量索引建立與維護。 | [Source: nexus/services/memory_indexer.py] |
| **Memory Embedding** | 協調 LLM Embedding API 呼叫。 | [Source: nexus/services/memory_embedding.py] |

## Upstream
- **[[System Overview]]**: 記憶系統導航。
- **[[Module - Intelligence and Context Core]]**: 提供查詢意圖與上下文包。

## Downstream
- **[[Module - Implementation Responsibility Matrix]]**: 記憶模組與物理檔案映射.
- **[[Ops - CI/CD Promotion Gate]]**: 記憶完整性作為發版審計標誌。

## Related modules / files
- `nexus/services/memory.py`: 記憶服務。 [Code: nexus/services/memory.py]
- `nexus/services/memory_repository.py`: 數據倉儲。 [Code: nexus/services/memory_repository.py]

## Source notes
- v22 Engine Spec: 要求長效記憶的召回延遲 (90th percentile) 不得超過 800ms。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Memory Tiering**: 是否需要將記憶分為 L1 (RAM) / L2 (SSD) / L3 (Archive) 三層。

---
Back to [[System Overview]]

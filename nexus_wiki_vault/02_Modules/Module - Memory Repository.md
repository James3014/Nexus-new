---
aliases:
- LanceDB
- Vector Memory Storage
confidence: high
last_compiled: 2026-04-06
owner: agent
raw_sources:
- nexus/services/memory_repository.py
- nexus/services/memory_embedding.py
related_pages:
- '[[Ops - Wisdom Layer|Ops - Wisdom Layer]]'
- '[[System Overview|System Overview]]'
- '[[System - Unknowns and Conflicts|Unknowns]] and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
- '[[State - Schemas|State - Schemas]]'
source_of_truth: nexus/services/memory_indexer.py
status: active
tags:
- module
- memory
- lancedb
- vector
- storage
title: Module - Memory Repository
type: module
version_scope:
- v22
- v23
---



# Module - Memory Repository

## One-sentence summary
本頁定義 Nexus 向量記憶體 (LanceDB) 的存儲架構、Schema 欄位與配額治理政策。

## Role / responsibility
- **持久化儲存**: 管理 `.nexus/memory/` 下的向量索引檔案。
- **高維檢索**: 提供 384 維度 (MiniLM-L6-v2) 的語義特徵搜尋。
- **經驗索引**: 將 `lesson_events.jsonl` 與 `manifest.json` 轉化為可檢索的知識節點。

## Upstream
- **Lesson Resolver**: 提供結構化教訓。 [Source: lesson_resolver.py]
- **Outcome Monitor**: 提供技能執行結果。 [Source: 00_Home/System Overview.md]
- **Embedding Service**: 提供 384 號向量化能力。 [Source: memory_embedding.py]

## Downstream
- **Wisdom Lookup**: 提供相似模式檢索與決策 Bias。 [Source: nexus_cli.py]
- **[[Ops - Wisdom Layer]]**: 作為智慧治理的底層基礎設施。

## Version Boundary Hardening (版本邊界硬化)
> [!IMPORTANT]
> **v23 Memory 定位**: v23 的智慧與學習能力是「建立在 v22 Production Baseline 之上的 Intelligence 增強層」。
> v23 的 `Online Learner` 與 `Bayesian Feedback` 機制係用於輔助治理決策，並不取代 v22 的 PDRAC 狀態契約或實體代碼權威。
> 所有 v23 產出的 `Wisdom` 標籤必須明確回指到 v22 的 `lesson_events.jsonl` 中，嚴禁發生版本語義坍塌。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]].md`]

## Storage Architecture
- **DB Path**: `.nexus/memory/memory_index.lancedb`
- **Table Name**: `memory_index`
- **Quotas (配額控制)**:
    - **Time Window**: 90 天 (僅保留最近 3 個月的活動數據)。 [Source: memory_indexer.py]
    - **Manifests**: Max 50 個最近任務清單。 [Source: memory_indexer.py]
    - **Outcome Events**: Max 1000 個技能成果事件。 [Source: memory_indexer.py]

## Entity Schema (MemoryIndexRecord)

| Field | Type | Description |
|---|---|---|
| `record_id` | string (SHA256) | 穩定 ID，用於冪等 Upsert (SHA256(record_type + key_ids))。 |
| `record_type` | enum | `local_lesson`, `shared_lesson`, `run_manifest`, `outcome_event`。 |
| `task_id` | string | 原始任務 ID。 |
| `trace_id` | string | 原始診斷 ID。 |
| `phase` | string | 產出該記錄的相位 (P/X/D/R/A/C)。 |
| `trust_tier` | enum | `local`, `peer`, `verified`。 |
| `created_at_utc`| string (ISO) | 記錄生成時間。 |
| `score_hint` | float (0-1) | 解析原始 Confidence 或 Pattern_Reuse 權重。 |
| `payload_json` | string (JSON) | 實體數據的 JSON 序列化封裝。 |
| `embedding` | Vector(384) | MiniLM 生成的高維語義特徵。 |

## Related modules / files
- `nexus/services/memory_indexer.py`: 核心索引建立器。
- `nexus/services/memory_repository.py`: LanceDB DAO 實作。

## Source notes
- memory_indexer.py L39-L54: 實體 Schema 定義。
- memory_indexer.py L21-L23: 磁碟配額定義。

## Open questions / conflicts
- [ ] **v23.1 Hybrid Table**: 是否需要為 `predictive_healing` 新增專屬的狀態表。
- [ ] **Search Fallback**: 當 FTS (Full Text Search) 失效時的 Regex 降級邏輯。

---
[[System Overview]]

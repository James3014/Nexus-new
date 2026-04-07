---
aliases:
- State Contracts
- JSON Schemas
confidence: high
last_compiled: 2026-04-06
owner: agent
raw_sources:
- plan_schema.json
- diagnosis_schema.json
- repair_final_schema.json
- audit_result_schema.json
- manifest_schema.json
related_pages:
- '[[State - Lifecycle|State - Lifecycle]]'
- '[[State - Schemas|State - Schemas]]'
- '[[System Overview|System Overview]]'
- '[[System - Unknowns and Conflicts|Unknowns]] and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: /Users/jameschen/Workspace/schemas/
status: active
tags:
- module
- state
- contracts
- json-schema
title: Module - State Contracts
type: module
version_scope:
- v17.1
- v22
- v23
---



# Module - State Contracts

## One-sentence summary
本頁定義 Nexus 任務執行過程中必須遵循的 5 大 JSON 狀態契約與跨檔案不變量。 [Reference: Spec v22]

## Role / responsibility
- **結構校驗**: 確保所有任務工件符合 `plan`, `diagnosis`, `repair`, `audit`, `manifest` 結構。 [Reference: manifest_schema.json]
- **不變量維護**: 強制要求 `task_id` 與 `trace_id` 在整個 Evidence Chain 中保持一致。 [Reference: Spec v22 Part 4.1]
- **風險分級**: 根據 `audit_result.json` 的 `risk_score` 決定門禁通過與否。 [Source: scripts/ops/ci_gate.py]

## Core Contracts Matrix

| Contract | Purpose | Key ID | Source Provenance |
|---|---|---|---|
| `plan.json` | 任務目標與 TODO | `task_id` | [Reference: plan_schema.json] |
| `diagnosis.json` | 現狀診斷與 Trace | `trace_id` | [Reference: diagnosis_schema.json] |
| `repair_final.json`| 修復方案與 Patch | `patch_hash` | [Reference: repair_final_schema.json] |
| `audit_result.json`| 審計風險評估 | `risk_score` | [Reference: audit_result_schema.json] |
| `manifest.json` | 最終證據封裝 | `seal_status` | [Reference: manifest_schema.json] |

## Upstream
- **Phase Runners**: 產出符合這些 Schema 的實體 JSON。 [Source: scripts/engine/nexus_cli.py]
- **Core Orchestrator**: 根據契約內容進行相位調度。 [Source: nexus/core/orchestrator.py]
- `nexus/core/handoff_bundle.py`: 狀態交接封裝邏輯。 [Source: nexus/core/handoff_bundle.py]
- v22 Engine Spec: 確立 `manifest.json` 為唯一權威索引。 [Reference: Spec v22]

## Downstream
- **[[System - Unknowns and Conflicts]]**: 登記 Schema 漂移衝突。
- **[[Ops - CI/CD Promotion Gate]]**: 基於契約數值執行發佈決策。

## Related modules / files
- `/Users/jameschen/Workspace/schemas/`: 實體 JSON Schema 定義。
- `nexus/core/handoff_bundle.py`: 狀態交接封裝邏輯。 [Code: 00_Home/System Overview.md]

## Source notes
- Hardened v17.1 Spec: 建立最初的 4 相位工件對位要求。
- v22 Engine Spec: 確立 `manifest.json` 為唯一權威索引。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Contract Versioning**: 預留 `contract_version` 欄位以支援跨版本的 Schema 兼容性。
- [ ] **Schema Evolution**: v23 智慧層是否應具備動態調整 Audit 閾值的能力。

---
[[System Overview]]
---
aliases:
- State Management
- Nexus State
- Snapshotting Engine
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[[Module - Platform Core Registry|Module - Platform Core Registry]]'
- '[[Module - Implementation Responsibility Matrix|Module - Implementation Responsibility
  Matrix]]'
source_of_truth: nexus/core/state_repository.py
status: active
tags:
- core
- state
- snapshot
- lifecycle
- persistence
title: Module - State Lifecycle and Snapshotting
type: module
version_scope:
- v22
- v23
---



# Module - State Lifecycle and Snapshotting

## One-sentence summary
本模組負責 Nexus 狀態機的物理持久化、版本管理、遷移驗證與心理/大腦快照捕獲。 [Source: nexus/core/state_repository.py]

## Role / responsibility
- **持久化保證**: 確保 Agent 的每一動狀態變遷皆被安全寫入 `.nexus/` 下的物理存儲。
- **快照捕獲**: 驅動 `BrainSnapshot` 與 `MentalSnapshot` 以支持任務回溯與自省。
- **遷移治理**: 處理從舊版 (v17) 到 v22/v23 的狀態結構遷移。

## State Component Registry (狀態組件登記)

| Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **State Repository** | JSONL 狀態流的主讀寫引擎。 | [Source: nexus/core/state_repository.py] |
| **State IO** | 物理路徑管理與檔案鎖控制。 | [Source: nexus/core/state_io.py] |
| **[[Module - State Contracts|State Contracts]]** | `NexusState` 數據結構與型別定義。 | [Source: nexus/core/state_contracts.py] |
| **State Migrator** | 不同版本架構間的數據遷移。 | [Source: nexus/core/state_migrator.py] |
| **State Validator** | 狀態完整性與邊界校驗。 | [Source: nexus/core/state_validator.py] |
| **State Legacy** | v17 與舊版 Nexus 狀態的墊片層。 | [Source: nexus/core/state_legacy.py] |
| **Brain Snapshot** | Agent 決定論背景的大腦快照捕獲。 | [Source: nexus/core/brain_snapshot.py] |
| **Mental Snapshot** | 運行時語義快照與上下文捕獲。 | [Source: nexus/core/mental_snapshot.py] |
| **Session Persistence** | Agent 交互會話的持久化與恢復。 | [Source: nexus/core/session_persistence.py] |
| **Migration Validator** | 遷移後的一致性自動對比。 | [Source: nexus/core/migration_validator.py] |

## Upstream
- **[[System Overview]]**: 全域狀態管理導航。
- **MUSE-NEXUS Spec**: 定義狀態機的原子性與持久化要求。

## Downstream
- **[[Module - Implementation Responsibility Matrix]]**: 持久化工具鏈與物理檔案映射。
- **[[Ops - CI/CD Promotion Gate]]**: 狀態完整性作為發版前的最後檢查。

## Related modules / files
- `nexus/core/state_repository.py`: 核心倉儲。 [Code: nexus/core/state_repository.py]
- `nexus/core/state_validator.py`: 驗證邏輯。 [Code: nexus/core/state_validator.py]
- `nexus/core/brain_snapshot.py`: 大腦快照。 [Code: nexus/core/brain_snapshot.py]

## Source notes
- v22 Engine Spec: 要求狀態寫入必須具備 "Fail-safe" 屬性，禁止殘留半完成的 JSON 損毀。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **State Compaction**: 隨著 JSONL 增長，是否需要自動觸發 L1/L2 壓縮任務。

---
Back to [[System Overview]]---
aliases:
- Memory Deep Dive
- RAG Pipeline
- Knowledge Flow
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[[Module - Intelligence and Context Core|Module - Intelligence and Context Core]]'
- '[[Module - Implementation Responsibility Matrix|Module - Implementation Responsibility
  Matrix]]'
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
本頁深入解析 Nexus 的長期記憶管道、[[Module - Memory Repository|LanceDB]] 整合細節與基於 Episode 的知識檢索流程。 [Source: nexus/services/memory.py]

## Role / responsibility
- **記憶存取控制**: 管理向量庫與物理文件系統間的數據交換。
- **語義召回 (RAG)**: 提供高性能的 Embedding 檢索引腳。
- **知識歸檔**: 負責將短期任務數據沉澱為長效治理資本。

## Memory Component Registry (記憶組件詳解)

| Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Memory Service** | 記憶管道的主入口與服務適配。 | [Source: nexus/services/memory.py] |
| **Memory Repository** | 實體 [[Module - Memory Repository|LanceDB]] 表與磁碟 IO 管理。 | [Source: nexus/services/memory_repository.py] |
| **Memory Indexer** | 高效率向量索引建立與維護。 | [Source: nexus/services/memory_indexer.py] |
| **Memory Embedding** | 協調 LLM Embedding [[api|API]] 呼叫。 | [Source: nexus/services/memory_embedding.py] |

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
- v22 Engine Spec: 要求長效記憶的召回延遲 (90th percentile) 不得超過 800ms。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Memory Tiering**: 是否需要將記憶分為 L1 (RAM) / L2 (SSD) / L3 (Archive) 三層。

---
Back to [[System Overview]]---
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

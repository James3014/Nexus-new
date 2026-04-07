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
Back to [[System Overview]]
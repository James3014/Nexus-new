---
aliases: '[Orchestrator Deep Dive, PDRAC Logic, Swarm Logic]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: nexus/core/swarm_orchestrator.py
status: active
tags: '[core, orchestrator, pdrac, swarm, logic, dive]'
title: '[Module - Core Orchestrator](Module - Core Orchestrator.md) Deep Dive'
type: module
version_scope: '[v22, v23]'
---



# [Module - Core Orchestrator](Module - Core Orchestrator.md) Deep Dive

> [!NOTE]
> **Canonical Page**: 本頁探討 `SwarmOrchestrator` 的微觀實作與多代理共識機制。量化指標與子命令架構請見 [Module - Core Orchestrator](Module - Core Orchestrator.md)。

## One-sentence summary
本頁深入探討 Nexus `SwarmOrchestrator` 的微觀執行邏輯、P-X-D-R-A-C 生命週期狀態機與多代理共識機制。 [Source: nexus/core/swarm_orchestrator.py]

## Role / responsibility
- **狀態遷移核心**: 管理從 Plan 到 Commit 的完整原子交易狀態流。 [Source: nexus/core/swarm_orchestrator.py]
- **並行衝突處理**: 確保多個代理在競爭同一資源時具備明確的鎖定與權益優先級。 [Source: nexus/core/state_repository.py]
- **故障自癒啟動**: 在偵測到執行停滯或異常時，觸發 `Self-Heal` 邏輯重啟任務圖。 [Source: nexus/core/orchestrator.py]

## Orchestrator Internal Logic (內部核心邏輯)

| Logic Block | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Consensus Engine** | 協調各個子代理對任務結果的最終一致性裁決。 | [Source: nexus/core/swarm_orchestrator.py] |
| **PDRAC Controller** | 實施 Plan -> Research -> Do -> Review -> Audit -> Commit 硬性階段。 | [Source: nexus/core/swarm_orchestrator.py] |
| **Wait Loop** | 非同步等待子任務完成並防止執行死結。 | [Source: nexus/core/swarm_orchestrator.py] |
| **State Synchronizer** | 將運行時狀態同步回 `StateRepository`。 | [Source: nexus/core/swarm_orchestrator.py] |

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 核心邏輯架構導航。
- **[Module - Task Scheduling and Swarm Adapters](Module - Task Scheduling and Swarm Adapters.md)**: 提供宏觀任務分片輸入。

## Downstream
- **[Module - Implementation Responsibility Matrix](Module - Implementation Responsibility Matrix.md)**: 提供實體檔案與邏輯功能的最終映射。
- **[[Ops - CI/CD Promotion Gate]]**: 狀態機正確性作為發版審計標誌。

## Related modules / files
- `nexus/core/swarm_orchestrator.py`: 核心協調器。 [Source: nexus/core/swarm_orchestrator.py]
- `nexus/core/task_graph.py`: 任務圖構建。 [Source: nexus/core/task_graph.py]

## Source notes
- v22 Engine Spec: 規定「禁止在 PDRAC 循環中跳過 Review 階段」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Timeout Strategy**: 當單個節點長時間無響應時的系統級超時熔斷時間。
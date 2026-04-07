---
aliases: '[Task](../Reference/task.md) Scheduling, Swarm Orchestration, K8s Adapter]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: nexus/core/swarm.py
status: active
tags: '[core, [task](../Reference/task.md), scheduling, swarm, k8s, sharding]'
title: Module - [Task](../Reference/task.md) Scheduling and Swarm Adapters
type: module
version_scope: '[v22, v23]'
---



# Module - [task](../Reference/task.md) Scheduling and Swarm Adapters

## One-sentence summary
本模組集合了 Nexus 的多代理協作、任務圖分片、並行執行調度與 Kubernetes Swarm 適配邏輯。 [Source: nexus/core/swarm.py]

## Role / responsibility
- **多代理調度**: 使用 `SwarmOrchestrator` 統籌多個執行個體的並行任務鏈。
- **任務分片**: 透過 `[task](../Reference/task.md) Sharding` 將複雜需求分解為相互依賴的 DAG (Directed Acyclic Graph) 節點。
- **物理集群接入**: 提供 K8s 適配層與 SSE 串流支持，實現分散式執行環境。

## Scheduling Component Registry (調度組件登記)

| Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Swarm Orchestrator** | 統籌多個子代理的執行狀態與訊息傳遞。 | [Source: nexus/core/swarm_orchestrator.py] |
| **[task](../Reference/task.md) Graph** | 任務依賴性 DAG 的構建。 | [Source: nexus/core/task_graph.py] |
| **Command DAG** | 底層 shell 指令執行鏈的拓撲。 | [Source: nexus/core/command_dag.py] |
| **[task](../Reference/task.md) Sharding** | 將大型任務切割為多個可並行子分片。 | [Source: nexus/core/task_sharding.py] |
| **Planner Executor** | Planner 指令的實體執行執行器。 | [Source: nexus/core/planner_executor.py] |
| **Planner Auditor** | 針對計畫執行結果進行獨立驗證。 | [Source: nexus/core/planner_auditor.py] |
| **K8s Swarm Adapter** | 實現 Nexus 核心與 K8s Pod 集群的通信。 | [Source: nexus/core/k8s_swarm_adapter.py] |
| **Swarm Base** | Swarm 的基礎類定義與心跳機制。 | [Source: nexus/core/swarm.py] |
| **SSE Support** | Nexus Swarm 的伺服器發送事件 (SSE) 串流實作。 | [Source: nexus/core/nexus_swarm_sse.py] |
| **Workspace Manager** | 虛擬執行空間的版本化管理與掛載。 | [Source: nexus/core/workspace_manager.py] |
| **Workspace Prefetch** | 預先獲取任務所需的檔案上下文與代碼段。 | [Source: nexus/core/workspace_prefetch.py] |
| **Dual Loop Orchestrator** | 支援「內部思考」與「外部行動」雙循環。 | [Source: nexus/core/dual_loop_orchestrator.py] |
| **Recursive Costing** | 計算遞迴任務調用的累積資源消耗。 | [Source: nexus/core/recursive_cost.py] |

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 全域分散式調度導航。
- **MUSE-NEXUS Spec**: 要求調度系統必須支援「原子回滾」與「狀態最終一致性」。

## Downstream
- **[Module - Implementation Responsibility Matrix](Module - Implementation Responsibility Matrix.md)**: 調度模組與物理檔案映射。
- **[Module - Core Orchestrator Deep Dive](Module - Core Orchestrator Deep Dive.md)**: 微觀執行階段邏輯對接。

## Related modules / files
- `nexus/core/swarm.py`: Swarm 基礎。 [Code: nexus/core/swarm.py]
- `nexus/core/task_graph.py`: 任務圖引擎。 [Code: nexus/core/task_graph.py]
- `nexus/core/task_sharding.py`: 分片邏輯。 [Code: nexus/core/task_sharding.py]

## Source notes
- v22 Engine Spec: 要求單個 Swarm 分片的大小不得超過 2048 字符指令。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Locking Mechanism**: 在 K8s 分散式環境下的文件寫入鎖競合處理。

---
Back to [System Overview](../00_Home/System Overview.md)

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]下的文件寫入鎖競合處理。

---
Back to [System Overview](../00_Home/System Overview.md)

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]
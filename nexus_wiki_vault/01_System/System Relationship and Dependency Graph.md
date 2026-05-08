---
aliases: '[System Map, Component Dependencies, Architecture Graph]'
confidence: high
last_compiled: '2026-04-21'
owner: agent
source_of_truth: repo-root-architecture
status: hardened
tags: '[system, architecture, graph, dependencies]'
title: System - Relationship & Dependency Graph
---

# System - Relationship & Dependency Graph (v26 Hardened)

## 1. 核心管線與領域解耦 (Today's Decoupled Update)
Nexus 已完成**治理層 (Governance)** 與 **事件層 (Events)** 的深度物理解耦。最新的組件交互如下：

```mermaid
graph TD
    A[Intent] -->|L4 Dispatch| B(CampaignGeneral)
    B -->|Task DAG| C{Tactical Drones}
    
    subgraph "Nerve Center (nexus/engine/)"
    D(Coordinator) -->|State| E(LoopManager)
    E --> F[cli_runner_async]
    end
    
    subgraph "Governance Shield (nexus/governance/)"
    G(HallucinationGuard)
    H(CapabilityGate)
    I(EvidenceGuard)
    end
    
    subgraph "Event Backbone (nexus/events/)"
    J(SignalIngress) --> K(LogStore)
    K --> L(Transport)
    end
    
    C -->|GBNF Actions| D
    F -->|Telemetry| J
    D -->|Evidence Bundle| G
    G -->|Scoring| H
    H -->|Tool Filter| C
    H -->|Verdict| I
    I -->|Promotion| M[Production]
```

## 2. 關鍵依賴變更 (April 21 Refactor)
- **事件層 (Events)**: 廢棄了舊有的 `event_bus.py` 單體架構，拆分為 `SignalIngress` (輸入)、`LogStore` (存儲) 與 `Transport` (傳輸)。
- **能力閘門 (CapabilityGate)**: 實施了「外觀模式 (Facade)」，實體邏輯移至 `nexus/governance/`，並在運行時根據 P-X-D-R-A-C 階段動態攔截 Agent 工具。
- **物理路徑校正**: 
    - `cli_runner_async.py` -> `nexus/engine/`
    - `capability_gate.py` -> `nexus/governance/`

---
Back to [[System Overview]]

## One-sentence summary
系統關係圖定義 L4-L3-L2 的核心依賴邊界與事件流向，作為架構變更的對位參考。

## Role / responsibility
- 提供組件邊界、依賴方向與監控對位的可讀圖譜，降低跨層變更風險。

## Upstream
- [[01_System/Code_Ownership_Matrix|Code Ownership Matrix]]
- [[01_System/Supreme_Master_Loop_Spec|Supreme_Master_Loop_Spec]]

## Downstream
- [[06_Ops/Ops - Architecture Decision Records|Architecture Decision Records]]
- [[05_Protocols/Protocol - Master Loop|Protocol - Master Loop]]

## Related modules / files
- [Source: compiled-wiki]
- [Source: 02_Modules/Module - Core Orchestrator.md]
- [[System Overview]]

## Source notes
- [Source: compiled-wiki]

## Open questions / conflicts
- Graph 邊界是否需要補上事件一致性保證的「回寫順序」欄位？

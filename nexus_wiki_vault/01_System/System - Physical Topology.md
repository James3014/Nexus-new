---
aliases:
- Deployment Architecture
- Physical Layout
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[System Overview](../00_Home/System Overview.md)'
- '[Unknowns](System - Unknowns and Conflicts.md) and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
- '[Module - Core Orchestrator](../02_Modules/Module - Core Orchestrator.md)'
source_of_truth: /Users/jameschen/Workspace/nexus/
status: active
tags:
- system
- - - Vault Topology|topology
- physical
- layout
title: System - Physical [Topology](../00_Home/Vault Topology.md)
type: system
version_scope:
- v17.1
- v22
- v23
---



# System - Physical [Topology](../00_Home/Vault Topology.md)

## One-sentence summary
本頁描述 Nexus 系統在檔案系統、執行序與存儲節點上的實體佈局與核心目錄結構。 [Reference: compiled-[topology](../00_Home/Vault Topology.md)]

## Role / responsibility
- **路徑權威**: 定義 `/Users/jameschen/Workspace/nexus/` 下的各目錄用途。 [Reference: [System Overview](../00_Home/System Overview.md)]
- **執行隔離**: 描述 `.venv` 環境與 Core 邏輯的區隔。 [Source: scripts/engine/nexus_cli.py]
- **持久化映射**: 定義 `.nexus/` 目錄與 [LanceDB](../02_Modules/Module - Memory Repository.md) 實體節點的關聯。 [Reference: [Module - Memory Repository](../02_Modules/Module - Memory Repository.md)]

## Physical Directory Hierarchy

| Root Path | Category | Purpose | Source Provenance |
|---|---|---|---|
| `.nexus/` | **State** | 存儲所有運行時狀態、報告與證據。 | [Reference: Spec v22 Part 6] |
| `.nexus/knowledge/`| **SSoT** | 存放 `policymemory.jsonl` 等真值。 | [Reference: /scripts/learning/cleanup_policy_memory.py] |
| `.nexus/memory/` | **Vector** | [LanceDB](../02_Modules/Module - Memory Repository.md) 向量資料庫節點。 | [Source: nexus/services/memory_indexer.py] |
| `nexus/` | **Logic** | 核心 Python 原始碼 (The Nerve)。 | [Source: 00_Home/System Overview.md] |
| `scripts/` | **Ops/Entry** | CLI 進入點與維運腳本。 | [Source: scripts/engine/nexus_cli.py] |
| `schemas/` | **Contract** | JSON Schema 權威定義中心。 | [Reference: [State - Schemas](../04_State/State - Schemas.md)] |

## Upstream
- **Deployment Spec**: 原始安裝與配置規範。
- **[System Overview](../00_Home/System Overview.md)**: 提供宏觀佈局指引。

## Downstream
- **[Module - Core Orchestrator](../02_Modules/Module - Core Orchestrator.md)**: 實體操作這些路徑。 [Code: 00_Home/System Overview.md]
- **[System - Unknowns and Conflicts](System - Unknowns and Conflicts.md)**: 登記路徑漂移或資源競爭問題。

## Related modules / files
- `/Users/jameschen/Workspace/nexus/`: 系統根路徑。
- `nexusnexus/.nexus/workspaces/bug-1774969963/nexus/core/errors.py`: 定義路徑缺失導致的 InfrastructureError。 [Code: 00_Home/System Overview.md]

## Source notes
- Hardened v17.1 Spec: 定義最初的 4 級目錄硬化結構。
- v22 Engine Spec: 引入 `.nexus/runs` 的階段化存儲路徑。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Permission Matrix**: 各目錄在不同用戶權限下的存取約束。
- [ ] **External Mount**: 部分龐大的向量資料庫是否應掛載於外部 Volume。

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]
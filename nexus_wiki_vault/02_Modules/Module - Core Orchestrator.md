---
aliases: '[Orchestrator Node, Nexus CLI Engine, Engine Master, NexusEngine]'
confidence: high
last_compiled: '2026-04-22'
owner: agent
raw_sources: 'nexus/core/orchestrator.py, nexus/core/state_contracts.py, scripts/engine/nexus_cli.py'
related_pages: '[[Module - Engine Service Registry]]'
source_of_truth: nexus/core/orchestrator.py
status: hardened
tags: '[module, core, orchestrator, engine, service_mesh, seam]'
title: Module - Core Orchestrator
---

# Module - Core Orchestrator (v26.2 Hardened Seams)

## One-sentence summary
本模組為 Nexus 的「動力引擎」，負責協調 L4 指揮層任務拆解與 L3 執行層的 P-X-D-R-A-C 閉環。

## 🛡️ 引擎與縫合點硬化 (April 22 Hardening)
在最近的重構中，Nexus 廢棄了所有的舊版回退機制（Legacy Fallbacks）：
- **Canonical Seam**: `campaign_master_loop` 現在強制透過 `execute_tactical_node` 委派工作。
- **Seam Function**: `_execute_via_canonical_service` 成為 L4 與 L3 交互的唯一物理入口。
- **No Legacy Fallback**: 移除 `scripts/v1.8_mega.py` 等舊版腳本的影子調用路徑。

## 🧱 服務網格化 (Service Mesh)
`NexusEngine` 將具備物理執行力的任務委派至以下核心服務：

| Domain | Key Service | Source (Path) |
| :--- | :--- | :--- |
| **Routing** | `AutonomicRoutingService` | `nexus/engine/autonomic_routing_service.py` |
| **Repair** | `RepairLoopService` | `nexus/engine/repair_loop_service.py` |
| **Seam** | `CanonicalTaskSeam` | `nexus/engine/canonical_task_seam.py` |

## ⚙️ 核心特徵
- **Atomic Init**: 所有服務由 `bootstrap.py` 原子化產出。
- **Seam Integrity**: 物理保證 L4 指揮官永遠不會越過 `Coordinator` 直接操作 Drone。

## Role / responsibility
- 聚合核心路由、審核與執行步驟，維持 Orchestrator 的行為可預期與可回溯。 [Source: nexus/core/orchestrator.py]
- 將服務註冊、路由決策、回傳訊息統一到單一執行框架。 [Source: nexus/engine/bootstrap.py]

## Upstream
- `nexus/core/orchestrator.py`：定義主循環節點與錯誤恢復。 [Source: nexus/core/orchestrator.py]
- `nexus/core/state_contracts.py`：規範 state 流轉。 [Source: nexus/core/state_contracts.py]

## Downstream
- 被 CLI 與 route smoke 調度呼叫，回傳 `NexusReceipt` 供驗證。 [Source: scripts/engine/nexus_cli.py]
- 影響 `nexus/core/policy_manager.py` 的 policy/event 記錄。 [Source: scripts/ops/ci_gate.py]

## Related modules / files
- `nexus/core/orchestrator.py`: 核心循環實作。 [Source: nexus/core/orchestrator.py]
- `nexus/core/state_contracts.py`: 狀態機與驗證邏輯。 [Source: nexus/core/state_contracts.py]
- `nexus/engine/bootstrap.py`: 初始化與服務組裝。 [Source: nexus/engine/bootstrap.py]

## Source notes
- 本頁以實際路徑回收為主，不以 legacy 文字說明覆蓋實作。 [Source: scripts/engine/nexus_cli.py]

## Open questions / conflicts
- [ ] 是否保留 `campaign_master_loop` 的同名替代流程，還是以新 seam 命名為主。 [Source: nexus/engine/bootstrap.py]

---
**[Source: nexus/core/orchestrator.py]**

[[System Overview]]

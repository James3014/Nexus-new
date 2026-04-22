---
aliases: '[Orchestrator Node, Nexus CLI Engine, Engine Master, NexusEngine]'
confidence: high
last_compiled: '2026-04-22'
owner: agent
raw_sources: 'nexus/engine/coordinator.py, nexus/engine/bootstrap.py, nexus/engine/cli_runner_async.py'
related_pages: '[[Module - Engine Service Registry]]'
source_of_truth: nexus/engine/coordinator.py
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

---
**[Source: nexus/engine/cli_runner_async.py | SEAM-HARDENED]**

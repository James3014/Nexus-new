---
aliases: '[Orchestrator Node, Nexus CLI Engine, Engine Master, NexusEngine]'
confidence: high
last_compiled: '2026-04-21'
owner: agent
raw_sources: 'nexus/engine/coordinator.py, nexus/engine/bootstrap.py'
related_pages: '[[Module - Engine Service Registry]]'
source_of_truth: nexus/engine/coordinator.py
status: hardened
tags: '[module, core, orchestrator, engine, service_mesh]'
title: Module - Core Orchestrator
---

# Module - Core Orchestrator (v26.1 Service Mesh)

## One-sentence summary
本模組為 Nexus 的「動力引擎」，在 v24.1 重構後演化為基於 **Service Mesh (服務網格)** 的分權架構，透過專屬 Service 處理路由、修復與結算。

## 🛡️ 引擎重構：從單體到服務化 (April 21 Refactor)
`NexusEngine` (原 Coordinator) 已被中空化，其核心職責現在由 `bootstrap.py` 初始化並注入的 20+ 個微型服務承擔：

| Domain | Service (實體服務) | Responsibility (職責) |
| :--- | :--- | :--- |
| **Routing** | `AutonomicRoutingService` | 執行基於記憶與領地的動態任務路由。 |
| **Repair** | `RepairLoopService` | 封裝補丁生成、驗證與熱修復循環。 |
| **Audit** | `ForecastGateService` | 預判治理門檻並攔截高風險變更。 |
| **Outcome** | `SubagentOutcomeService` | 統整子代理執行結果與誠信證據。 |
| **Closure** | `CrystallizationService` | 執行任務封印與教訓結晶化。 |

## ⚙️ 核心特徵
- **Dependency Injection (DI)**: 所有的組件均由 `build_engine_components` 統一產出並注入引擎。
- **Service Decoupling**: 引擎僅負責 Phase 轉發，具體邏輯物理隔離在各個 `*_service.py` 檔案中。

---
**[Source: nexus/engine/coordinator.py | MESH-ALIGNED]**

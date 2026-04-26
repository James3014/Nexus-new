---
aliases: '[Service List, Engine Micro-Services, MESH_INDEX]'
confidence: high
last_compiled: '2026-04-21'
owner: agent
source_of_truth: nexus/engine/bootstrap.py
status: hardened
tags: '[core, mesh, services, registry]'
title: Module - Engine Service Registry
---

# Module - Engine Service Registry (v26.1 Hardened)

## One-sentence summary
本文件作為 Nexus Engine 內部所有微型服務的「全典索引」，記錄每個服務的物理路徑、職責與 PPhase 對位。

## ⚙️ 引擎服務全典 (Full Service Index)

| Service Name | Package | Physical Path | Primary Duty (主要職責) |
| :--- | :--- | :--- | :--- |
| **AutonomicRouting** | `engine` | `nexus/engine/autonomic_routing_service.py` | 決策意圖路由。 |
| **RepairSetup** | `engine` | `nexus/engine/repair_setup_service.py` | 初始化補丁環境。 |
| **RepairAttempt** | `engine` | `nexus/engine/repair_attempt_service.py` | 執行物理修復動作。 |
| **RepairLoop** | `engine` | `nexus/engine/repair_loop_service.py` | 管理修復重試邏輯。 |
| **ForecastGate** | `engine` | `nexus/engine/forecast_gate_service.py` | 任務風險預判。 |
| **DirectMode** | `engine` | `nexus/engine/direct_mode.py` | 快速直連執行模式。 |
| **SignalQueue** | `events` | `nexus/events/signal_queue_service.py` | 管理信號進程隊列。 |
| **BenchmarkService** | `learn` | `nexus/research/learn/benchmark_service.py` | 執行 A/B 指標對標。 |
| **ReportService** | `learn` | `nexus/research/learn/report_service.py` | 生成學習結項報告。 |
| **SourceRegistry** | `learn` | `nexus/research/learn/source_registry_service.py`| 管理學習源與引用鏈。 |

## 🛡️ 實體執行規約
- **Atomic Init**: 所有服務必須由 `bootstrap.build_engine_components` 進行原子化初始化。
- **Contract-First**: 服務間通訊嚴禁直接修改對象狀態，必須透過傳遞 Pydantic `Artifact` 進行。

---
**[Source: April 21 Massive Refactor | MISSION-SEALED]**

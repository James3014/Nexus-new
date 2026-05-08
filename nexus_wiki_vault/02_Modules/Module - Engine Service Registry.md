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

## Role / responsibility
- 建立並維護 `nexus/engine` 服務清單，界定每個服務的職責、觸發條件與輸入輸出。 [Source: nexus/engine/bootstrap.py]
- 支援 CI/路由/記憶相關能力的註冊與健康檢查邏輯。 [Source: scripts/ops/ci_gate.py]

## Upstream
- `nexus/engine/bootstrap.py` 管理服務匯流樞紐。 [Source: nexus/engine/bootstrap.py]

## Downstream
- 被 `Module - Core Orchestrator` 與 `Module - Domain Services and Adapters` 作為服務總表參考。 [Source: scripts/engine/nexus_cli.py]

## Related modules / files
- `nexus/engine/bootstrap.py`: 服務組裝入口。 [Source: nexus/engine/bootstrap.py]
- `scripts/ops/ci_gate.py`: 提供 registry 與 route smoke 的驗收。 [Source: scripts/ops/ci_gate.py]

## Source notes
- service index 為 runtime 可驗證的硬件映射，避免口頭記憶導向。 [Source: scripts/engine/nexus_cli.py]

## Open questions / conflicts
- [ ] `repair_setup_service.py`、`repair_attempt_service.py` 是否仍為實作主路徑，需確認是否已移除。 [Source: nexus/engine/bootstrap.py]
- [ ] `nexus/research/learn/source_registry_service.py` 是否已被重構整合。 [Source: scripts/ops/wiki_linter.py]

---
**[Source: scripts/engine/nexus_cli.py]**

[[System Overview]]

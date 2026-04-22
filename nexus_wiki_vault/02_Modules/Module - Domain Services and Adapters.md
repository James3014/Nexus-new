---
aliases: '[Domain Services, Nexus Services, Service Mesh, Engine Registry]'
confidence: high
last_compiled: '2026-04-21'
owner: agent
raw_sources: 'nexus/engine/bootstrap.py, nexus/services/registry.py'
related_pages: '[[17_UNIFIED_SERVICE_REGISTRY_AND_MESH_V1]]'
source_of_truth: nexus/engine/bootstrap.py
status: hardened
tags: '[services, adapter, registry, mesh]'
title: Module - Domain Services & Engine Registry
---

# Module - Domain Services & Engine Registry (v26.1 Hardened)

## One-sentence summary
本模組集合了 Nexus 的所有領域服務，並透過 `bootstrap.py` 實施集中化組件註冊與服務網格 (Service Mesh) 管理。

## 🧱 引擎組件註冊中心 (Engine Registry)
Nexus 透過 `build_engine_components` 在啟動時完成物理接線。所有的服務現在均以「單例服務 (Service-as-a-Singleton)」的形式運行。

### 🛠️ 核心服務網格 (Core Service Mesh)

| Category | Service Name | Physical Path |
| :--- | :--- | :--- |
| **Engine** | `AutonomicRouting` | `nexus/engine/autonomic_routing_service.py` |
| **Engine** | `ForecastGate` | `nexus/engine/forecast_gate_service.py` |
| **Engine** | `RepairLoop` | `nexus/engine/repair_loop_service.py` |
| **Engine** | `SubagentOutcome` | `nexus/engine/subagent_outcome_service.py` |
| **Learn** | `BenchmarkService` | `nexus/research/learn/benchmark_service.py` |
| **Learn** | `ReportService` | `nexus/research/learn/report_service.py` |
| **Events** | `SignalQueue` | `nexus/events/signal_queue_service.py` |

## 🛡️ 治理規範 (Governance Rules)
1. **Lazy Binding**: 非核心服務應使用延遲加載以優化 L4 指揮層的啟動時間。
2. **Standard Interfaces**: 每個 Service 必須回傳標準化的 `Decision` 或 `Artifact` 對象。
3. **No Legacy Seams**: 嚴禁在引擎外層調用已標註為 `legacy` 的舊版 `coordinator` 直接實例化方法。

---
**[Source: nexus/engine/bootstrap.py | APRIL-21-MESH]**

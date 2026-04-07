---
aliases:
- Core Shell
- Nexus Platform Core
- Utility Matrix
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[System Overview](../00_Home/System Overview.md)'
- '[Module - Implementation Responsibility
  Matrix](Module - Implementation Responsibility Matrix.md)'
source_of_truth: nexus/core/hubs.py
status: active
tags:
- core
- platform
- utilities
- hubs
- metrics
title: Module - Platform Core Registry
type: module
version_scope:
- v22
- v23
---



# Module - Platform Core Registry

## One-sentence summary
本模組集合了 Nexus 系統運行的基礎設施、錯誤代碼、元數據指標與核心 Hubs 統籌邏輯。 [Source: nexus/core/hubs.py]

## Role / responsibility
- **基礎設施初始化**: 定義 `NexusInfraHub` 作為系統物理資源的單一接入點。
- **全域元數據管控**: 透過 `MetricsAggregator` 進行全系統性能鏈路監控。
- **異常標準化**: 提供統一的 `NexusError` 與 OS 級別的 `exit_codes.py` 映射。

## Core Component Registry (核心組件登記)

| Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Hubs Dispatcher** | 協調 Infra, Intel, Gov 三大樞紐。 | [Source: nexus/core/hubs.py] |
| **System Config** | 全域參數與 YAML 載入。 | [Source: nexus/core/config.py] |
| **Deferred Loader** | 延遲加載組件以優化啟動。 | [Source: nexus/core/deferred_loader.py] |
| **Dual Sink** | 雙路輸出標記。 | [Source: nexus/core/dual_sink.py] |
| **Events Hub** | 異步事件總線。 | [Source: nexus/core/events.py] |
| **Outcome Schema** | 執行結果的 Schema 契約。 | [Source: nexus/core/outcome_schema.py] |
| **Preflight Check** | 啟動前的硬體與環境檢查。 | [Source: nexus/core/preflight_check.py] |
| **Protocols Core** | 基礎協議定義。 | [Source: nexus/core/protocols.py] |
| **Error Definitions** | Nexus 客製化異常類。 | [Source: nexus/core/errors.py] |
| **Exit Codes** | CLI 退出碼規範。 | [Source: nexus/core/exit_codes.py] |
| **Metrics Writer** | 性能數據物理寫入。 | [Source: nexus/core/metrics_writer.py] |
| **Metrics Aggregator** | 週期性指標彙整。 | [Source: nexus/core/metrics_aggregator.py] |
| **Notification System** | 系統層級警告與事件通知。 | [Source: nexus/core/notifier.py] |
| **Minimal Tracer** | 輕量化路徑追蹤與日誌。 | [Source: nexus/core/minimal_tracer.py] |
| **Recursive Cost** | 遞迴成本估算邏輯。 | [Source: nexus/core/recursive_cost.py] |
| **Cost Hook** | 攔截工具調用並計費。 | [Source: nexus/core/cost_hook.py] |
| **Event Bus** | 內部組件非同步通訊。 | [Source: nexus/core/event_bus.py] |
| **Action Brief** | 任務指令摘要格式化。 | [Source: nexus/core/action_brief.py] |
| **Agent Awareness** | Agent 自我感官狀態維護。 | [Source: nexus/core/agent_awareness.py] |

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 提供本模組的全域上下文導航。
- **MUSE-NEXUS Spec**: 定義 Core 層級的初始化規範。

## Downstream
- **[Module - Implementation Responsibility Matrix](Module - Implementation Responsibility Matrix.md)**: 提供實體檔案與功能職責的具體映射。
- **[[Ops - CI/CD Promotion Gate]]**: 元數據與指標作為發版依據。

## Related modules / files
- `nexus/core/hubs.py`: 核心樞紐。 [Code: nexus/core/hubs.py]
- `nexus/core/config.py`: 系統配置。 [Code: nexus/core/config.py]
- `nexus/core/errors.py`: 錯誤定義。 [Code: nexus/core/errors.py]

## Source notes
- v22 Engine Spec: 要求基礎設施必須在 500ms 內完成冷啟動初始化。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Notifier Scale**: 是否需要對接外部 Webhook (如 Discord/Slack) 的標準模組。

---
Back to [System Overview](../00_Home/System Overview.md)

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]
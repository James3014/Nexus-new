---
aliases: '[Orchestrator Node, Nexus CLI Engine, Engine Master]'
confidence: high
last_compiled: '2026-04-21'
owner: agent
raw_sources: 'nexus/engine/cli_runner_async.py, nexus/core/dual_loop_orchestrator.py'
related_pages: '[[Supreme_Master_Loop_Spec]]'
source_of_truth: nexus/engine/cli_runner_async.py
status: hardened
tags: '[module, core, orchestrator, controller, engine]'
title: Module - Core Orchestrator
type: module
version_scope: '[v24.1, v26]'
---

# Module - Core Orchestrator (v26 Hardened)

## One-sentence summary
本模組為 Nexus 的「動力引擎」，負責協調 L4 指揮層任務拆解與 L3 執行層的 P-X-D-R-A-C 閉環，並產出 v24.1 標竿級交付憑證。

## Role / responsibility
- **引擎位移 (Engine Move)**: 核心主循環 `campaign_master_loop` 已遷移至 `nexus/engine/cli_runner_async.py` 進行邏輯解耦。
- **交付憑證 (Delivery Receipt)**: 任務完成後由 `nexus/delivery/receipt.py` 產出物理收據，包含 SHA256 驗證與八大誠信步驟。
- **並發誠信**: 使用 `threading.RLock` 確保事件廣播與狀態更新的原子性，物理阻斷死鎖。 [Source: nexus/core/event_bus.py]

## Related modules / files
- `nexus/engine/cli_runner_async.py`: 非同步執行主循環 (L4/L3 橋接)。
- `nexus/delivery/receipt.py`: 產出 v24.1-canonical 交付收據。
- `nexus/core/event_bus.py`: 具備可重入鎖 (RLock) 的系統脈搏。

---
Back to [[System Overview]]

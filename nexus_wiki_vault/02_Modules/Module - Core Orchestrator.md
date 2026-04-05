---
title: Module - Core Orchestrator
aliases: [Orchestrator Node, Nexus CLI Engine]
type: module
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: scripts/engine/nexus_cli.py
raw_sources:
  - nexus/core/orchestrator.py
  - nexus/core/state_machine.py
related_pages:
  - "[[Module - Runtime Services]]"
  - "[[Flow - PXDRAC Runtime]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [module, core, orchestrator, controller]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Module - Core Orchestrator

## One-sentence summary
本模組為 Nexus Swarm 的「神經中樞」，負責接收任務指令、調度 Phase Runners 並維護全域狀態機。 [Source: `nexus_cli.py`]

## Role / responsibility
- **命令解析**: 處理 `nexus:*` 全系列子命令與參數校驗。 [Code: `nexus_cli.py`]
- **調度序列**: 驅動 P-X-D-R-A-C 流程的物理執行。 [Source: Page: Flow - PXDRAC Runtime]
- **異步門禁**: 在 TTY 模式下執行 `Pilot CLI` 的交互監聽與風險阻斷。 [Code: `pilot_cli.py`]

## Upstream
- **User Interface (CLI)**: 原始命令輸入流。
- **Wisdom Layer (v23)**: 提供決策權重與 Bias 修正。 [Source: v23 Wisdom]

## Downstream
- **Phase Runners**: 調用具體的業務執行實體。 [Code: `nexus_plan.py`, `nexus_diagnose.py` etc.]
- **[[Module - State Contracts]]**: 確保交接工件符合 JSON Schema。

## Related modules / files
- `nexus/core/orchestrator.py`: 核心業務管理類。 [Code: `orchestrator.py`]
- `nexus/core/state_machine.py`: 狀態轉移權威邏輯。 [Code: `state_machine.py`]

## Source notes
- Hardened v17.1 Spec: 定義原始 Orchestrator 的核心責任清單。
- v22 Engine Spec: 加入了對 `manifest.json` 與 `handoff_bundle` 的原生支援。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Concurrency**: 多任務併發時鎖定 `.nexus/` 的資源競爭處理。
- [ ] **External API**: 是否需要開放 FastAPI 入口以支援 Nexus Desk 介面調用。

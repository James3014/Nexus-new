---
aliases: '[Orchestrator Node, Nexus CLI Engine]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
raw_sources: ''
related_pages: ''
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags: '[module, core, orchestrator, controller]'
title: Module - Core Orchestrator
type: module
version_scope: '[v17.1, v22, v23]'
---



# Module - Core Orchestrator

> [!NOTE]
> **Canonical Page**: 本頁為 Nexus Orchestrator 的高階權威定義。技術細節與微觀實作請參閱 [Module - Core Orchestrator Deep Dive](Module - Core Orchestrator Deep Dive.md)。

## One-sentence summary
本模組為 Nexus Swarm 的「神經中樞」，負責接收任務指令、調度 Phase Runners 並維護全域狀態機。 [Source: scripts/engine/nexus_cli.py]

## Role / responsibility
- **命令解析**: 處理 `nexus:*` 全系列子命令與參數校驗。 [Source: scripts/engine/nexus_cli.py]
- **調度序列**: 驅動 P-X-D-R-A-C 流程的物理執行。 [Source: nexus_wiki_vault/03_Flows/Flow - PXDRAC Runtime.md]]]
- **異步門禁**: 在 TTY 模式下執行 `Pilot CLI` 的交互監聽與風險阻斷。 [Source: nexus/core/orchestrator.py]

## Upstream
- **User Interface (CLI)**: 原始命令輸入流。
- **Wisdom Layer (v23)**: 提供決策權重與 Bias 修正。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]]]

## Downstream
- **Phase Runners**: 調用具體的業務執行實體。 [Source: nexus/core/orchestrator.py]
- **[Module - State Contracts](Module - State Contracts.md)**: 確保交接工件符合 JSON Schema。

## Related modules / files
- `nexus/core/orchestrator.py`: 核心業務管理類。 [Source: nexus/core/orchestrator.py]
- `nexus/core/state_machine.py`: 狀態轉移權威邏輯。 [Source: nexus/core/state_machine.py]

## Source notes
- Hardened v17.1 Spec: 定義原始 Orchestrator 的核心責任清單。
- v22 Engine Spec: 加入了對 `manifest.json` 與 `handoff_bundle` 的原生支援。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Concurrency**: 多任務併發時鎖定 `.nexus/` 的資源競爭處理。
- [ ] **External [[api|API]]**: 是否需要開放 FastAPI 入口以支援 [Nexus Desk](Module - Nexus Desk Interface.md) 介面調用。

---
[System Overview](../00_Home/System Overview.md)

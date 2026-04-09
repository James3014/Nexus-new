---
'- [[MUSE_ENGINE_SPEC|v23 Wisdom]] notes [Source': '[[MUSE_ENGINE_SPEC|MUSE_ENGINE_SPEC]]]'
aliases: '[Nexus Overview, Home, NEXUS_OS]'
confidence: high
last_compiled: '2026-04-07'
owner: agent
raw_sources: ''
related_pages: ''
source_of_truth: compiled-wiki
status: active
tags: '[home, overview, nexus]'
title: System Overview
type: home
version_scope: '[v22, v23]'
---



# System Overview

## One-sentence summary
Nexus 是一個以 **P-X-D-R-A-C** 為主生命週期、以 `.nexus` 與 schema/artifact 為 production truth、並在 v22 穩定主線上疊加 v23 智慧層的多代理治理系統。

## Role / responsibility
- **v22**: 負責 production readiness、orchestration、self-healing、governance 與 release discipline。
    - **[NEW] Phase 8 (Autonomous Integrity)**: 引入 Context Shield、ReAct 修復迴圈與 Rollback 保護。
- **v23**: 負責 wisdom memory、online learning、predictive healing 與 consensus guard。
- **定位**: 作為 Nexus Swarm 的編排平向 (Governance Plane)，確保任務執行具有可追溯性與智慧演化能力。

## Upstream
- **PDRAC vs [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]**: v17.1 的 PDRAC 流程在 v22 中擴展為 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] (新增 `X` 探查相位)。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **CLI Drift**: v23 引入了 `--risk` 等智慧參數。 [Source: nexus_wiki_vault/05_Protocols/Protocol - CLI Drift Matrix.md]]]

## Downstream
- **Codebase**: 執行檔案修改、測試執行。
- **.[nexus State](../02_Modules/Module - State Lifecycle and Snapshotting.md)**: 輸出 metrics、reports 與證據工件- **v22 (Stable Baseline)**: 原生生產力基線。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **v23 (Intelligence Layer)**: 疊加於 v22 之上的智慧治理層。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]] Supplement]

## Navigation (治理與開發入口)

### 🗺️ Knowledge & Heritage (地圖與遺產)
- **[Vault Topology](Vault Topology.md)**: [New] 知識庫全景拓撲圖。
- **[[01_Core/Specs/Legacy_V9/INDEX|Legacy V9 Index]]**: [Imported] Nexus V9 核心架構與穩定化歷史。
- **[[01_Core/Specs/Muse-Nexus-v152-upgrade/INDEX|v152 Upgrade Index]]**: [Imported] v152 關鍵升級路徑與環境變數。

### 🚀 [Onboarding](Agent Onboarding - Command Pack.md) & Ops
- **[Agent Boot Sequence](Agent Boot Sequence.md)**: 新 Agent 前 30 分鐘啟動 SOP。
- **[CLI Surface Quickstart](CLI Surface Quickstart.md)**: 任務常用 CLI 最小命令集。
- **[Agent Onboarding - Command Pack](Agent Onboarding - Command Pack.md)**: 常用指令速查。
- **[Ops - CI Failure Playbook](../06_Ops/Ops - CI Failure Playbook.md)**: CI 失敗修復指南。
- **[Agent Onboarding - Implementation Map](Agent Onboarding - Implementation Map.md)**: 實作路徑地圖。

### 🛡️ 治理合規與規約 (Governance & Protocols)
- **[Protocol - Engineering Discipline](../05_Protocols/Protocol%20-%20Engineering%20Discipline.md)**: [New] 反合理化與 TDD 強制規範。
- **[Protocol - Context Hygiene](../05_Protocols/Protocol%20-%20Context%20Hygiene.md)**: [New] Context Shield 與日誌長度物理護欄。
- **[Flow - Recursive Auto-Repair](../03_Flows/Flow%20-%20Recursive%20Auto-Repair.md)**: [New] ReAct 自治修復與回滾機制流程。
- **[Ops - Governance Changelog](../06_Ops/Ops - Governance Changelog.md)**: 治理變更日誌。

### 🛡️ Governance & Quality
- **[Ops - Truth Claims Register](../06_Ops/Ops - Truth Claims Register.md)**: 實體真值驗證表。
- **[Source - Coverage Heatmap](../90_Sources/Source - Coverage Heatmap.md)**: Wiki 覆蓋率熱圖。
- **[Ops - Wiki Drift Audit](../06_Ops/Ops - Wiki Drift Audit.md)**: 物理路徑漂移稽核。
- **[Ops - Wiki Regression Evals](../06_Ops/Ops - Wiki Regression Evals.md)**: [New] Wiki 知識回歸測試。
- **[Module - Implementation Responsibility Matrix](../02_Modules/Module - Implementation Responsibility Matrix.md)**: 代碼責任矩陣。

### 🧠 Core Modules (Deep Dives)
- **[Nexus Glossary](../01_System/Nexus Glossary.md)**: 核心術語與語義對齊入口。
- **[Module - Core Orchestrator Deep Dive](../02_Modules/Module - Core Orchestrator Deep Dive.md)**: 編排引擎深描。
- **[Module - Guard and Gate Control](../02_Modules/Module - Guard and Gate Control.md)**: 工具閘門控制。
- **[Module - Memory Pipeline Deep Dive](../02_Modules/Module - Memory Pipeline Deep Dive.md)**: 記憶體管道與 [LanceDB](../02_Modules/Module - Memory Repository.md)。
- **[Module - Policy and Learning Governance](../02_Modules/Module - Policy and Learning Governance.md)**: 政策管理與學習。

## Related modules / files
- `nexus/core/`- **[Orchestrator Node](../02_Modules/Module - Core Orchestrator.md)**: 位於 `./`。 [Code: scripts/engine/nexus_cli.py]
- **Vast State**: `.nexus/` 目錄。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

### Module Registry (全系統組件登記)
- **[Module - Implementation Responsibility Matrix](../02_Modules/Module - Implementation Responsibility Matrix.md)**: [P0] 核心功能與物理檔案映射總表。
- **[Module - Platform Core Registry](../02_Modules/Module - Platform Core Registry.md)**: [New] 基礎設施與核心 Hubs 登記。
- **[Module - State Lifecycle and Snapshotting](../02_Modules/Module - State Lifecycle and Snapshotting.md)**: [New] 狀態機與快照引擎登記。
- **[Module - Security and Tool Guard Registry](../02_Modules/Module - Security and Tool Guard Registry.md)**: [New] 安全防禦與工具鎖定登記。
- **[Module - Intelligence and Context Core](../02_Modules/Module - Intelligence and Context Core.md)**: [New] 語義上下文與 RAG 登記。
- **[Module - Task Scheduling and Swarm Adapters](../02_Modules/Module - Task Scheduling and Swarm Adapters.md)**: [New] 任務調度與並行協作登記。
- **[Module - Domain Services and Adapters](../02_Modules/Module - Domain Services and Adapters.md)**: [New] 外部服務與適配器登記。
- **[Module - Intelligence and Logic - Remaining Core.md)](../02_Modules/Module - Intelligence and Logic - Remaining Core.md)**: [New] 剩餘核心邏輯登記。
- **[Module - Advanced Core Intelligence](../02_Modules/Module - Advanced Core Intelligence.md)**: [New] Ash 矩陣與進階政策登記。
- **[Source - Operational Scripts Index](../90_Sources/Source - Operational Scripts Index.md)**: [New] 全量維運與引擎腳本索引。

### 🛡️ 治理維運 (Operations & Governance)
- **[Ops - Weekly Governance Report](../06_Ops/Ops - Weekly Governance Report.md)**: 每週治理健康度與風險摘要。
- **[Ops - Wiki Page Type Contracts](../06_Ops/Ops - Wiki Page Type Contracts.md)**: [New] Wiki 頁面類型契約。
- **[Ops - Query Writeback Policy](../06_Ops/Ops - Query Writeback Policy.md)**: [New] 查詢回寫至 Wiki 政策。
- **[Ops - Governance SLO Dashboard](../06_Ops/Ops - Governance SLO Dashboard.md)**: 治理指標趨勢面板。
- **[Ops - Architecture Decision Records](../06_Ops/Ops - Architecture Decision Records.md)**: 架構決策脈絡與取捨索引。
- **[Ops - Optimization Proposal Protocol](../06_Ops/Ops - Optimization Proposal Protocol.md)**: 優化提案提交與驗收模板。
- **[Ops - Agent Capability Boundaries](../06_Ops/Ops - Agent Capability Boundaries.md)**: 代理改動邊界與 HITL 規則。
- **[Ops - Learning Closure Matrix](../06_Ops/Ops - Learning Closure Matrix.md)**: 錯誤類型到防再發策略矩陣。
- **[Ops - Wiki Drift Audit](../06_Ops/Ops - Wiki Drift Audit.md)**: 實體與文檔漂移監控。
- **[Ops - Wiki Link Integrity](../06_Ops/Ops - Wiki Link Integrity.md)**: 連結完整性與孤兒頁。
- **[Ops - Reference Boundary and Archive Policy](../06_Ops/Ops - Reference Boundary and Archive Policy.md)**: Reference 保留邊界與封存治理。
- **[Ops - Closeout Hard Gate](../06_Ops/Ops - Closeout Hard Gate.md)**: 完成回報前的 done contract 阻斷閘門。
- **[Ops - Ownership and Review SLA](../06_Ops/Ops - Ownership and Review SLA.md)**: 頁面所有權與編校年資平衡。
- **[Ops - Truth Claims Register](../06_Ops/Ops - Truth Claims Register.md)**: 真相宣稱與自動化驗證。
- **[Ops - Governance Changelog](../06_Ops/Ops - Governance Changelog.md)**: 治理變更歷史路徑。
- **[Ops - CI Failure Playbook](../06_Ops/Ops - CI Failure Playbook.md)**: [New] CI 紅燈故障排除 20 案手冊。

(State Hub)

## Source notes
- MUSE-NEXUS Engine Specification v22: 定義 P-X-D-R-A-C 相位矩陣與基礎契約。
- [[MUSE_ENGINE_SPEC|v23 Wisdom]] notes: 定義智慧治理層與貝氏學習迴圈。
- MUSE-NEXUS Engine Specification v17.1 Hardened: 提供物理拓撲與硬化門禁歷史。

## Open questions / conflicts
- [ ] 哪些頁面應進一步拆成模組頁（如 [State Contracts](../02_Modules/Module - State Contracts.md)）。
- [ ] 針對 PDRAC 與 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] 的語義漂移進行對位。


---
[System Overview](System Overview.md)
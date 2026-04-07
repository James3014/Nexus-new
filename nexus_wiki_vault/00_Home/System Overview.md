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
- **v23**: 負責 wisdom memory、online learning、predictive healing 與 consensus guard。
- **定位**: 作為 Nexus Swarm 的編排平向 (Governance Plane)，確保任務執行具有可追溯性與智慧演化能力。

## Upstream
- **PDRAC vs [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]**: v17.1 的 PDRAC 流程在 v22 中擴展為 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] (新增 `X` 探查相位)。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **CLI Drift**: v23 引入了 `--risk` 等智慧參數。 [Source: nexus_wiki_vault/05_Protocols/Protocol - CLI Drift Matrix.md]]]

## Downstream
- **Codebase**: 執行檔案修改、測試執行。
- **.[[Module - State Lifecycle and Snapshotting|nexus State]]**: 輸出 metrics、reports 與證據工件- **v22 (Stable Baseline)**: 原生生產力基線。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **v23 (Intelligence Layer)**: 疊加於 v22 之上的智慧治理層。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]] Supplement]

## Navigation (治理與開發入口)

### 🗺️ Knowledge & Heritage (地圖與遺產)
- **[[Vault Topology]]**: [New] 知識庫全景拓撲圖。
- **[[01_Core/Specs/Legacy_V9/INDEX|Legacy V9 Index]]**: [Imported] Nexus V9 核心架構與穩定化歷史。
- **[[01_Core/Specs/Muse-Nexus-v152-upgrade/INDEX|v152 Upgrade Index]]**: [Imported] v152 關鍵升級路徑與環境變數。

### 🚀 [[Agent Onboarding - Command Pack|Onboarding]] & Ops
- **[[Agent Boot Sequence]]**: 新 Agent 前 30 分鐘啟動 SOP。
- **[[CLI Surface Quickstart]]**: 任務常用 CLI 最小命令集。
- **[[Agent Onboarding - Command Pack]]**: 常用指令速查。
- **[[Ops - CI Failure Playbook]]**: CI 失敗修復指南。
- **[[Agent Onboarding - Implementation Map]]**: 實作路徑地圖。
- **[[Ops - Governance Changelog]]**: 治理變更日誌。

### 🛡️ Governance & Quality
- **[[Ops - Truth Claims Register]]**: 實體真值驗證表。
- **[[Source - Coverage Heatmap]]**: Wiki 覆蓋率熱圖。
- **[[Ops - Wiki Drift Audit]]**: 物理路徑漂移稽核。
- **[[Ops - Wiki Regression Evals]]**: [New] Wiki 知識回歸測試。
- **[[Module - Implementation Responsibility Matrix]]**: 代碼責任矩陣。

### 🧠 Core Modules (Deep Dives)
- **[[Nexus Glossary]]**: 核心術語與語義對齊入口。
- **[[Module - Core Orchestrator Deep Dive]]**: 編排引擎深描。
- **[[Module - Guard and Gate Control]]**: 工具閘門控制。
- **[[Module - Memory Pipeline Deep Dive]]**: 記憶體管道與 [[Module - Memory Repository|LanceDB]]。
- **[[Module - Policy and Learning Governance]]**: 政策管理與學習。

## Related modules / files
- `nexus/core/`- **[[Module - Core Orchestrator|Orchestrator Node]]**: 位於 `/Users/jameschen/Workspace/nexus/`。 [Code: nexus_cli.py]
- **Vast State**: `.nexus/` 目錄。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

### Module Registry (全系統組件登記)
- **[[Module - Implementation Responsibility Matrix]]**: [P0] 核心功能與物理檔案映射總表。
- **[[Module - Platform Core Registry]]**: [New] 基礎設施與核心 Hubs 登記。
- **[[Module - State Lifecycle and Snapshotting]]**: [New] 狀態機與快照引擎登記。
- **[[Module - Security and Tool Guard Registry]]**: [New] 安全防禦與工具鎖定登記。
- **[[Module - Intelligence and Context Core]]**: [New] 語義上下文與 RAG 登記。
- **[[Module - Task Scheduling and Swarm Adapters]]**: [New] 任務調度與並行協作登記。
- **[[Module - Domain Services and Adapters]]**: [New] 外部服務與適配器登記。
- **[[Module - Intelligence and Logic (Remaining Core)]]**: [New] 剩餘核心邏輯登記。
- **[[Module - Advanced Core Intelligence]]**: [New] Ash 矩陣與進階政策登記。
- **[[Source - Operational Scripts Index]]**: [New] 全量維運與引擎腳本索引。

### 🛡️ 治理維運 (Operations & Governance)
- **[[Ops - Weekly Governance Report]]**: 每週治理健康度與風險摘要。
- **[[Ops - Wiki Page Type Contracts]]**: [New] Wiki 頁面類型契約。
- **[[Ops - Query Writeback Policy]]**: [New] 查詢回寫至 Wiki 政策。
- **[[Ops - Governance SLO Dashboard]]**: 治理指標趨勢面板。
- **[[Ops - Architecture Decision Records]]**: 架構決策脈絡與取捨索引。
- **[[Ops - Optimization Proposal Protocol]]**: 優化提案提交與驗收模板。
- **[[Ops - Agent Capability Boundaries]]**: 代理改動邊界與 HITL 規則。
- **[[Ops - Learning Closure Matrix]]**: 錯誤類型到防再發策略矩陣。
- **[[Ops - Wiki Drift Audit]]**: 實體與文檔漂移監控。
- **[[Ops - Wiki Link Integrity]]**: 連結完整性與孤兒頁。
- **[[Ops - Reference Boundary and Archive Policy]]**: Reference 保留邊界與封存治理。
- **[[Ops - Closeout Hard Gate]]**: 完成回報前的 done contract 阻斷閘門。
- **[[Ops - Ownership and Review SLA]]**: 頁面所有權與編校年資平衡。
- **[[Ops - Truth Claims Register]]**: 真相宣稱與自動化驗證。
- **[[Ops - Governance Changelog]]**: 治理變更歷史路徑。
- **[[Ops - CI Failure Playbook]]**: [New] CI 紅燈故障排除 20 案手冊。

(State Hub)

## Source notes
- MUSE-NEXUS Engine Specification v22: 定義 P-X-D-R-A-C 相位矩陣與基礎契約。
- [[MUSE_ENGINE_SPEC|v23 Wisdom]] notes: 定義智慧治理層與貝氏學習迴圈。
- MUSE-NEXUS Engine Specification v17.1 Hardened: 提供物理拓撲與硬化門禁歷史。

## Open questions / conflicts
- [ ] 哪些頁面應進一步拆成模組頁（如 [[Module - State Contracts|State Contracts]]）。
- [ ] 針對 PDRAC 與 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] 的語義漂移進行對位。

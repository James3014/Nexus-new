---
aliases: '[Nexus Overview, Home, NEXUS_OS]'
confidence: high
last_compiled: '2026-07-13'
owner: agent
source_of_truth: compiled-wiki
status: hardened
tags: '[home, overview, nexus]'
title: System Overview
type: home
version_scope: '[v24, v25, v26, v28]'
---

# System Overview (v28.3 Fleet Command)

## 歡迎來到 Nexus 治理作業系統
Nexus 是一個以物理誠信為核心、為 AI Agent Swarm 打造的自動化 P-X-D-R-A-C 治理環境。

---

## 角色導航入口 (Persona Portals)
請選擇您的角色以獲取專屬導航：
- **[[README_Product|產品導覽]]** | **[[README_Investor|投資人簡報]]**
- **[[README_Agent|Agent 執碼規約]]** | **[[README_Contributor|貢獻者指南]]**
- **[[CURRENT_STATE|Current State]]** | **[[AGENT_BOOTSTRAP|Agent Bootstrap]]** | **[[PARTNER_ONBOARDING|Partner Onboarding]]**

---

## 治理與維護規則
- **[[99_Schema/WIKI_GOVERNANCE_CHARTER|Wiki 結構憲法]]**: 架構凍結與增頁規約。
- **[[99_Schema/Wiki_Changelog_Auto|維基演化日誌]]**: 最近變更追蹤。

---

## 三大任務主線 (The Three Mainlines)
1. **認識 Nexus (Understand)**: [[00_Product/User Stories|User Stories]] | [[05_Commercial/Go-to-Market|Business Plan]]
2. **操作 Nexus (Operate)**: [[07_Compliance/Governance - Capability Gate and Tool Isolation|Capability Gate]] | [[05_Protocols/CLI_Full_Params|CLI Reference]]
3. **追溯 Nexus (Trace)**: [[99_Schema/Page_Version_Matrix|Page Maturity Matrix]] | [[08_Diffs/Code_to_Wiki_Alignment_Matrix|Alignment Matrix]]

---

## 三條執行鏈 (2026-07-13 驗證)

Nexus 目前存在三條獨立執行路徑：

| 世界 | 名稱 | 入口 | 用途 | 狀態 |
|------|------|------|------|------|
| **A** | Agent-Operated Nexus | `enforced.sh` -> Gemini CLI -> nexus CLI | 日常開發治理 | governance wearing proven |
| **B** | Benchmark A/B Harness | `capability_ab_runner.py` -> LocalModelExecutor | 證明 uplift | Bare vs Nexus 比較 |
| **C** | Local Armor Executor | `LocalModelExecutor.run()` | 本地模型執行 | benchmark runtime proven |

**最大缺口**：World A 與 World C 之間沒有 runtime bridge。World B 是驗證儀器，不是產品主線。

詳細分析見 [[01_System/SYSTEM_ARCHITECTURE_BLUEPRINT#16. 三條執行鏈與架構缺口 (2026-07-13 驗證)|架構缺口分析]]。

---
**[NEXUS IDENTITY: e148a212 + v32.6 REFACTOR-SEALED]**

## One-sentence summary
系統總覽頁定義 Nexus 的治理作業模型、核心角色入口與三大任務主線，作為全域導航與信任錨點。

## Role / responsibility
- 提供全域入口、任務主線與治理鏈路索引，統一各角色語義對位。

## Upstream
- [[01_System/MUSE_PROTO|MUSE_PROTO]]
- [[06_Ops/Ops - Wiki Page Type Contracts|Wiki Page Type Contracts]]

## Downstream
- [[00_Home/README_Product|README_Product]]
- [[00_Home/README_Agent|README_Agent]]
- [[00_Home/README_Contributor|README_Contributor]]

## Related modules / files
- [Source: 01_System/MUSE_PROTO.md]
- [Source: 05_Protocols/Protocol - CLI Drift Matrix.md]
- [Source: 00_Home/README_Product.md]

## Source notes
- 2026-07-13: 更新三條執行鏈分析與架構缺口。

## Open questions / conflicts
- Governance 與 runtime route 能否共用單一「健康閾值」而非分層指標，避免重複解讀？
- 如何在不改變 World A 控制鏈的前提下，讓 LocalModelExecutor 成為 Canonical CLI 的正式 backend？

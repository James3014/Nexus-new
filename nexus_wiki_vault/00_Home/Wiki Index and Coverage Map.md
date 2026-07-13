---
aliases: '[Wiki Index and Coverage Map, Home Index]'
confidence: high
last_compiled: '2026-05-06'
owner: agent
source_of_truth: compiled-wiki
status: active
tags: '[home, index, governance]'
title: Wiki Index and Coverage Map
type: home
version_scope: '[v30]'
---

# 🗺️ Nexus Wiki Index & Coverage Map (v30.3 Final)
**[PHYSICAL_STATUS: STRUCTURE_FROZEN | VERSION_V30.3]**

## 🛡️ 總導覽：Nexus 產品與治理全景入口
本 Wiki 的資訊架構現已正式凍結。未來僅允許「增頁」與「內容更新」，嚴禁新增平行主目錄。

---

## 🧭 三大任務主線 (Core Mainlines)

### 🧩 認識 Nexus (Understand)
面向產品與生態。
- **Current State**: [[00_Home/CURRENT_STATE|CURRENT_STATE]]
- **產品首頁**: [[00_Home/README_Product|README_Product]]
- **數據工程**: [[04_Research/Data_Engineering/NEXUS_FULL_SPECTRUM_DATA_ENGINEERING_ATLAS|Data Engineering Atlas]]
- **使用者案例**: [[00_Product/User Stories|User Stories]]
- **商業戰略**: [[05_Commercial/Go-to-Market|Go-to-Market]]
- **投資人簡報**: [[00_Product/Investor Deck|Investor Deck]]

### ⚙️ 操作 Nexus (Operate)
面向執行與開發。
- **Agent Bootstrap**: [[00_Home/AGENT_BOOTSTRAP|AGENT_BOOTSTRAP]]
- **Partner Onboarding**: [[00_Home/PARTNER_ONBOARDING|PARTNER_ONBOARDING]]
- **Claim Taxonomy**: [[01_System/CLAIM_TAXONOMY|CLAIM_TAXONOMY]]
- **最高規約**: [[01_System/MUSE_PROTO|MUSE_PROTO v2.4]]
- **進化白皮書**: [[01_System/Evolution/LEARNING_EVOLUTION_MANIFESTO|Evolution Manifesto]]
- **架構藍圖**: [[01_System/SYSTEM_ARCHITECTURE_BLUEPRINT|System Blueprint]]
- **能力矩陣**: [[02_Modules/Module - Capability Matrix|Capability Matrix (v26)]]
- **路由協議**: [[05_Protocols/Protocol - Capability Routing|Capability Routing Protocol]]
- **CLI 手冊**: [[05_Protocols/CLI_Full_Params|CLI Full Parameters]]
- **能力矩陣**: [[01_System/16_CAPABILITY_SPEC_MATRIX|Capability Matrix]]

### 🗺️ 專案計劃與狀態 (Status & Plans)
- **[能力路由狀態總表 (2026-04-30)](../../docs/arch/CAPABILITY_ROUTE_STATUS_2026-04-30.md)**
- **[能力路由遷移計劃 (2026-04-29)](../../docs/arch/CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29.md)**
- **[智慧路由整合長計劃 v2](../../docs/arch/NEXUS_ROUTING_LONG_PLAN_V2.md)**

### 📜 追溯 Nexus (Trace)
面向審計與歷史。
- **Authority Manifest**: [[99_Schema/WIKI_AUTHORITY_MANIFEST|WIKI_AUTHORITY_MANIFEST.yaml]]
- **決策日誌 (ADR)**: [[01_System/ADR/|Recent ADRs (2026-05)]]
- **演化日誌**: [[99_Schema/Wiki_Changelog_Auto|Automatic Changelog]]
- **驗收狀態**: [[04_State/NEXUS_FINAL_ACCEPTANCE_MATRIX_2026-05-06|Final Acceptance Matrix]]
- **路線圖**: [[09_Roadmap/CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29|Migration Roadmap]]
- **文碼對位**: [[08_Diffs/Code_to_Wiki_Alignment_Matrix|Alignment Matrix]]

---

## 📊 物理目錄對位表 (Physical Directory Sync)

| Layer | Directory | Content | Status |
| :--- | :--- | :--- | :--- |
| **L0** | `00_Product/` | 商業與使用者案例。 | ✅ **SYNCED** |
| **L1** | `01_System/` | 核心術語與系統全景。 | ✅ **SYNCED** |
| **L2** | `05_Protocols/`| 執行規約與 CLI 標準。 | ✅ **SYNCED** |
| **L3** | `02_Modules/` | 硬化後的組件規格。 | ✅ **SYNCED** |
| **L4** | `06_Ops/` | 維運、發布與恢復 SOP。| ✅ **SYNCED** |
| **L5** | `05_Commercial/`| 市場路徑與合規。 | ✅ **SYNCED** |
| **L6** | `06_Ecosystem/` | SDK 與 API 參考。 | ✅ **SYNCED** |

---
**[NEXUS v30.3 IDENTITY: STRUCTURE-FROZEN | SSOT]**

## One-sentence summary
這是 Nexus Wiki 的主索引與 coverage 對位頁，提供入口、任務主線與目錄對位的整體導航。

## Role / responsibility
- 導向各角色與任務線，維持文件結構一致性與導覽可信度。

## Upstream
- [[System Overview]]
- [[01_System/System - Unknowns and Conflicts|System - Unknowns and Conflicts]]

## Downstream
- [[00_Product/User Stories|User Stories]]
- [[99_Schema/Page_Version_Matrix|Page Maturity Matrix]]
- [[08_Diffs/Code_to_Wiki_Alignment_Matrix|Code-to-Wiki Alignment]]

## Related modules / files
- [Source: 90_Sources/Source - Coverage Heatmap.md]
- [[00_Home/README_Product|README_Product]]
- [[05_Protocols/Protocol - CLI Drift Matrix|Protocol - CLI Drift Matrix]]

## Source notes
- [Source: compiled-wiki]

## Open questions / conflicts
- 與 00_Product 的長尾頁面索引是否應該同步列入以避免 dead-link 機制風險？

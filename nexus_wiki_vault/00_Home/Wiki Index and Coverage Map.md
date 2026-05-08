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
- **產品首頁**: [[00_Home/README_Product|README_Product]]
- **使用者案例**: [[00_Product/User Stories|User Stories]]
- **商業戰略**: [[05_Commercial/Go-to-Market|Go-to-Market]]
- **投資人簡報**: [[00_Product/Investor Deck|Investor Deck]]

### ⚙️ 操作 Nexus (Operate)
面向執行與開發。
- **最高規約**: [[01_System/MUSE_PROTO|MUSE_PROTO v2.4]]
- **CLI 手冊**: [[05_Protocols/CLI_Full_Params|CLI Full Parameters]]
- **故障修復**: [[06_Ops/Ops - CI Failure Playbook|Failure Playbook]]
- **審計計分**: [[07_Compliance/Hallucination_Guard_Scoring_Spec|HI Scoring Spec]]

### 📜 追溯 Nexus (Trace)
面向審計與歷史。
- **演化日誌**: [[99_Schema/Wiki_Changelog_Auto|Automatic Changelog]]
- **健康矩陣**: [[99_Schema/Page_Version_Matrix|Page Maturity Matrix]]
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

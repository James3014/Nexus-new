---
aliases:
- Provenance Waivers
- Exception Registry
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[System Overview](../00_Home/System Overview.md)'
- '[Index](../.nexus/graph/index.md)|[[Source [[index|Index]]|Source [Index](../.nexus/graph/index.md)]]]]'
- '[Unknowns](../01_System/System - Unknowns and Conflicts.md) and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: compiled-governance
status: active
tags:
- ops
- provenance
- - - exceptions|exceptions
- waivers
title: Ops - Provenance [[exceptions|Exceptions]] and Waivers
type: ops
version_scope:
- v17.1
- v22
- v23
---



# Ops - Provenance [[exceptions]] and Waivers

## One-sentence summary
本頁集中登記 Wiki 內容中因歷史原因、代碼轉型需求或外部第三方限制而無法物理回指 Repo 實體路徑的例外項 (Waivers)。 [Source: 00_Home/System Overview.md]

## Role / responsibility
- **例外管控**: 提供 Linter 跳過特定文件或段落路徑檢查的權威機器可讀資料來源。 [Source: scripts/ops/wiki_linter.py]
- **硬性審核**: 任何 Waiver 都必須包含 7 大必填欄位：`ID, Page, Owner, Reason, Type, Expiry, ApprovedBy`。 [Source: 00_Home/System Overview.md]
- **透明治理**: 標註哪些知識節點目前處於「軟溯源」狀態，防止治理黑洞。

## Active Waivers Registry (例外註冊表)

| ID | Page | Owner | Reason | Type | Expiry | ApprovedBy |
|---|---|---|---|---|---|---|
| `W-01` | **[System Overview](../00_Home/System Overview.md)** | `agent` | 早期哲學描述存於 v17.1 Slack。 | `Legacy` | 2026-12 | `nexus_admin` |
| `W-02` | **Wise - Consensus** | `agent` | v23 共識層 Bias 為人類經驗調參。 | `Wisdom` | 2026-08 | `james_chen` |
| `W-03` | **Network [Topology](../00_Home/Vault Topology.md)**| `agent` | 外部 Arweave 節點無法本地驗證。 | `External` | 2099-12 | `nexus_admin` |
| `W-04` | **Provenance Virtual**| `agent` | `compiled-*` 類虛擬治理標籤。 | `Internal` | 2099-12 | `nexus_admin` |
| `[[MUSE_ENGINE_SPEC|W-05]]` | **Wisdom Draft** | `agent` | v23 智慧層開發中腳本 (v22 未實作)。 | `Draft` | 2026-06 | `agent` |

## Upstream
- **[System - Unknowns and Conflicts](../01_System/System - Unknowns and Conflicts.md)**: 登記發現的溯源斷裂。
- **Wiki Linter**: 自動提示需要豁免的路徑檢查失敗。 [Source: scripts/ops/wiki_linter.py]

## Downstream
- **Wiki Linter**: 讀取本頁內容作為路徑校驗的「白名單」。 [Code: scripts/ops/wiki_linter.py]

## Related modules / files
- `scripts/ops/scripts/ops/wiki_linter.py`: 實體校驗引擎。 [Code: scripts/ops/wiki_linter.py]
- `99_Schema/[AGENT_SCHEMA](../99_Schema/AGENT_SCHEMA.md).md`: 治理規約。 [Source: 00_Home/System Overview.md]

## Source notes
- v22 Engine Spec: 確立「受控例外優於隱藏錯誤」的治理原則。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Automated Expiry**: 是否應在 Expiry 到期後自動撤銷 Linter 豁免。
- [ ] **Waiver Audit**: 是否需要定期（按季度）審計所有已發放的 Waiver。
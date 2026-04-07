---
aliases: '[Nexus Anti [Index](../.nexus/graph/index.md)|[Index](../.nexus/graph/index.md)|[Index](../.nexus/graph/index.md)|[[Source [[index|Index]]|Sources]]]]]]]],
  External Research Registry]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: compiled-[index](../.nexus/graph/index.md)
status: active
tags: '[Index](../.nexus/graph/index.md)|[Index](../.nexus/graph/index.md)|[Index](../.nexus/graph/index.md)|[[Source [[index|Index]]|sources]]]]]]]],
  external, registry, nexus-anti]'
title: Source - Nexus Anti Registry
type: system
version_scope: '[v17.1, v22, v23]'
---



# Source - Nexus Anti Registry

## One-sentence summary
本頁登記 `nexus-anti` 外部資料的用途與可信等級，將其定位為「歷史/分析參考層」而非 production truth。 [Source: nexus_wiki_vault/99_Schema/AGENT_SCHEMA.md]].md]

## Role / responsibility
- 明確區分可作為真值的 repo 實體路徑，與只可作為分析參考的外部文檔。 [Source: scripts/ops/wiki_linter.py]
- 提供 future agent 的導入守則，避免把外部分析報告直接寫入核心契約頁。 [Source: nexus_wiki_vault/00_Home/System Overview.md]].md]
- 提供「候選補件」清單，要求先有 repo 物理證據再升級到 Wiki 真值層。 [Source: nexus_wiki_vault/06_Ops/Ops - Provenance Exceptions and Waivers.md]].md]

## Upstream
- `nexus-anti` 文件集合（策略/審計/設計/比較報告）。 [Source: nexus_wiki_vault/90_Sources/Source Index.md]].md]
- v22/v17.1 規格書歷史版本。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Downstream
- 核心 Wiki 頁面僅吸收「可被 repo 路徑驗證」的內容。 [Source: scripts/ops/wiki_linter.py]
- 需引用外部文件時，先在本頁登記為 reference，再進行實作落地。 [Source: nexus_wiki_vault/06_Ops/Ops - CI/CD Promotion Gate.md]].md]

## Related modules / files
- `nexus_wiki_vault/90_Sources/[Source Index](Source Index.md).md`: 主來源索引頁。 [Source: nexus_wiki_vault/90_Sources/Source Index.md]].md]
- `scripts/ops/wiki_linter.py`: provenance/path 驗證規則。 [Source: scripts/ops/wiki_linter.py]
- `MUSE-NEXUS-Engine-Specification-v22-Eternal.md`: 現行主規格。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- `MUSE_ENGINE_SPEC_V17.1_HARDENED.md`: legacy 規格。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Source notes
- `nexus-anti` 中的審計/市場比較/策略文檔，可用於提案與歷史脈絡，不可直接替代 repo 物理真值。 [Source: nexus_wiki_vault/00_Home/System Overview.md]].md]
- 若外部文檔聲稱某功能已上線，必須在 repo 內找到對應路徑（程式、schema、工件）才可升格為 Wiki 真值陳述。 [Source: scripts/ops/wiki_linter.py]

## Open questions / conflicts
- [ ] 是否為 `nexus-anti` 建立定期同步流程（僅抽取可驗證條目）。
- [ ] 是否需要新增「External Claim -> Repo Proof」自動比對腳本。

## External Reference Classification
| Class | Typical files in `nexus-anti` | Can be copied into truth pages directly? | Rule |
|---|---|---|---|
| Historical spec mirrors | v17.1/v22 規格副本 | No | 只能引用 repo 主規格頁，不以外部副本作為最終來源 |
| Strategic analysis | SWOT / market comparison / design consultation | No | 只能作為提案背景 |
| Audit reports | [[qa|QA]]/review/refactor reports | Conditional | 需先對位到 repo 可驗證路徑 |
| Proposed implementation notes | 例如 [LanceDB](../02_Modules/Module - Memory Repository.md) 補充提案 | Conditional | 先落地代碼與工件，再升級到真值頁 |

## Related modules / files
- [System Overview](../00_Home/System Overview.md)
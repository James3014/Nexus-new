---
title: Protocol - Knowledge Lineage
aliases: [Lineage Map, Knowledge Data Fabric]
type: protocol
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: MUSE-NEXUS-v22#DataFabric
related_pages:
  - "[[Module - State Contracts]]"
  - "[[Protocol - Evidence Map]]"
  - "[[Module - Memory Repository]]"
  - "[[Ops - Artifact Retention and Provenance]]"
  - "[[Ops - CI/CD Promotion Gate]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [protocol, knowledge, lineage, fabric]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Protocol - Knowledge Lineage

## One-sentence summary
本頁呈現 Nexus 從 Runtime 工件到長期記憶與治理決策的完整知識血緣全景圖。 [Source: Spec v22 Part 5]

## Role / responsibility
- **全景視覺化**: 將破碎的 Wiki 頁面串聯成單一的知識演化流向圖。 [Source: Page: System Overview]
- **生命週期追蹤**: 描述知識如何從「瞬時狀態」萃取為「智慧經驗」。 [Source: Page: Module - Memory Repository]
- **治理校準**: 確保 Lineage 中的每一個節點都有對應的 Wiki 治理定義。 [Source: Page: Ops - Provenance Exceptions and Waivers]

## Knowledge Lineage Map (全血緣地圖)

```mermaid
graph LR
    subgraph "Phase 1: Runtime Context"
        SC[["Module - State Contracts"]] --> |"Phase Results"| EM[["Protocol - Evidence Map"]]
    end

    subgraph "Phase 2: Crystallization"
        EM --> |"Manifest Sealing"| EC[["Protocol - Evidence Chain"]]
        EC --> |"Lesson Extraction"| MR[["Module - Memory Repository"]]
    end

    subgraph "Phase 3: Persistence & Governance"
        MR --> |"Vector Index"| WL[["Ops - Wisdom Layer"]]
        MR --> |"Cleanup Policy"| RP[["Ops - Artifact Retention and Provenance"]]
    end

    subgraph "Phase 4: Promotion"
        WL --> |"Bias Feedback"| PG[["Ops - CI/CD Promotion Gate"]]
        RP --> |"Evidence Verification"| PG
    end

    subgraph "Cycle: Intelligence Loop"
        PG --> |"Evolution"| SC
    end
```

## Upstream
- **[[System Overview]]**: 提供宏觀數據演化背景。
- **Runtime Trace**: 實體任務執行紀錄。

## Downstream
- **[[Ops - Wisdom Layer]]**: 指導智慧層的教訓應用。
- **[[Ops - CI/CD Promotion Gate]]**: 提供全鏈路審核證據。

## Related modules / files
- `05_Protocols/Protocol - Evidence Map.md`: 原始證據圖譜。 [Source: Page: Protocol - Evidence Map]
- `06_Ops/Ops - Artifact Retention and Provenance.md`: 保存政策。 [Source: Page: Ops - Artifact Retention and Provenance]

## Source notes
- v22 Engine Spec: 確立 Knowledge Lineage 作為 Data Fabric 的最高層現。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Lineage Drift**: 智慧層產出的決策是否應建立獨立的血緣分支。
- [ ] **Storage Tiers**: 線上 (Hot) 與 離線 (Cold) 知識資產在 Lineage 中的區隔顯示。

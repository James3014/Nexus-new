---
aliases:
- Evidence Map
- Artifact Linkage
confidence: high
last_compiled: 2026-04-06
owner: agent
raw_sources:
- MUSE-NEXUS Engine Specification v22
- MUSE-NEXUS Engine Specification v17.1
- manifest_schema.json
related_pages:
- '[State Contracts](../02_Modules/Module - State Contracts.md)|[[Module - [[Module - State Contracts|State
  Contracts]]|Module - [State Contracts](../02_Modules/Module - State Contracts.md)]]]]'
- '[Protocol - Evidence Chain](Protocol - Evidence Chain.md)'
- Ops - CI/[Promotion Gate](../06_Ops/Ops - CI/CD Promotion Gate.md)|[[CD [[CD Promotion Gate|Promotion
  Gate]]|CD [Promotion Gate](../06_Ops/Ops - CI/CD Promotion Gate.md)]]]]
- '[System Overview](../00_Home/System Overview.md)'
- '[Unknowns](../01_System/System - Unknowns and Conflicts.md) and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: compiled-wiki
status: active
tags:
- protocol
- evidence
- map
- trace
title: Protocol - Evidence Map
type: protocol
version_scope:
- v17.1
- v22
- v23
---



# Protocol - Evidence Map

## One-sentence summary
本頁定義 Nexus 任務執行過程中工件 (Artifacts) 之間的依賴圖譜、產生者與門禁關鍵度。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Role / responsibility
- **地圖導航**: 呈現從 Planning 到 Crystallize 的資料流向。 [Source: nexus_cli.py]
- **對帳追蹤**: 標註 `task_id` 與 `trace_id` 在不同階段的責任變更。 [Source: 00_Home/System Overview.md]
- **門禁可視化**: 標註哪些工件是 [Promotion Gate](../06_Ops/Ops - CI/CD Promotion Gate.md) 的強制輸入。 [Source: ci_gate.py]

## Upstream
- **Phase P-R**: 產出原始 JSON 工件。 [Source: 02_Modules/Module - State Contracts.md]]]
- **Manifest Sealer**: 彙整全量證據。 [Source: 00_Home/System Overview.md]

## Downstream
- **[[Ops - CI/CD Promotion Gate]]**: 提供指標對位的實體證據。
- **[System - Unknowns and Conflicts](../01_System/System - Unknowns and Conflicts.md)**: 登記工件鏈斷裂衝突。

## Evidence Dependency Map

```mermaid
graph TD
    subgraph "Phase P: Planning"
        P1[plan.json] --> |"task_id"| D1
    end

    subgraph "Phase D: Diagnosis"
        D1[diagnosis.json] --> |"trace_id"| R1
    end

    subgraph "Phase R: Repair"
        R1[repair_final.json] --> |"task_id + trace_id + patch_hash"| A1
    end

    subgraph "Phase A: Audit"
        A1[audit_result.json] --> |"audit_trace_id -> Ref: trace_id"| M1
        A1 --> |"revision"| M1
    end

    subgraph "Phase C: Crystallize"
        M1[manifest.json] --> |"Seal Status: LOCKED"| C1[lesson_events.jsonl]
    end

    subgraph "v23 Intelligence"
        C1 --> |"Vectorize"| W1[[[Module - Memory Repository|Wisdom Memory]]]
        W1 --> |"Bias / Feedback"| P1
    end
```

## Evidence Alignment Matrix (高保真對位矩陣)

| Artifact | Producer (產生者) | Gate Criticality | Retention Path | Source File |
|---|---|---|---|---|
| `plan.json` | Planner (P) | MEDIUM | `.nexus/runs/<id>/` | [Source: 00_Home/System Overview.md] |
| `diagnosis.json` | Diagnoser (D) | **HIGH** | `.nexus/runs/<id>/` | [Source: 00_Home/System Overview.md] |
| `repair_final.json`| Repairer (R) | **HIGH** | `.nexus/runs/<id>/` | [Source: 00_Home/System Overview.md] |
| `write_proof.json` | Repairer (R) | **CRITICAL** | `.nexus/runs/<id>/` | [Source: ci_gate.py] |
| `audit_result.json`| Auditor (A) | **CRITICAL** | `.nexus/runs/<id>/` | [Source: 00_Home/System Overview.md] |
| `manifest.json` | Manifest Sealer (C) | **CRITICAL** | Root: `manifest.json` | [Source: 00_Home/System Overview.md] |
| `lesson_events.jsonl`| Crystallizer (C) | MEDIUM | `.nexus/knowledge/` | [Source: /nexus/services/memory_indexer.py] |

## Related modules / files
- `.nexus/runs/`: 任務實體存放區。
- `manifest.json`: 全量工件索引。 [Source: 00_Home/System Overview.md]

## Source notes
- Hardened v17.1 Spec: 定義 4.1 跨檔一致性與 6.1 Manifest 索引。
- v22 Engine Spec: 確立 SSoT 必須同步至 `.nexus/knowledge/`。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Handoff Path**: v23.1 的 `last_handoff.json` 在地圖中的精確切入點。
- [ ] **Drift Register**: 如何在地圖中標註「預期工件缺失」的處理邏輯。

---
[System Overview](../00_Home/System Overview.md)

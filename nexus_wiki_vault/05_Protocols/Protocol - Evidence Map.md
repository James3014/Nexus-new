---
title: Protocol - Evidence Map
aliases: [Evidence Map, Artifact Linkage]
type: protocol
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: compiled-wiki
raw_sources:
  - MUSE-NEXUS Engine Specification v22
  - MUSE-NEXUS Engine Specification v17.1
  - manifest_schema.json
related_pages:
  - "[[Module - State Contracts]]"
  - "[[Protocol - Evidence Chain]]"
  - "[[Ops - CI/CD Promotion Gate]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [protocol, evidence, map, trace]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Protocol - Evidence Map

## One-sentence summary
本頁定義 Nexus 任務執行過程中工件 (Artifacts) 之間的依賴圖譜、產生者與門禁關鍵度。 [Source: Spec v22]

## Role / responsibility
- **地圖導航**: 呈現從 Planning 到 Crystallize 的資料流向。 [Source: `nexus_cli.py`]
- **對帳追蹤**: 標註 `task_id` 與 `trace_id` 在不同階段的責任變更。 [Source: `manifest_schema.json`]
- **門禁可視化**: 標註哪些工件是 Promotion Gate 的強制輸入。 [Source: `ci_gate.py`]

## Upstream
- **Phase P-R**: 產出原始 JSON 工件。 [Source: Page: Module - State Contracts]
- **Manifest Sealer**: 彙整全量證據。 [Source: `manifest_schema.json`]

## Downstream
- **[[Ops - CI/CD Promotion Gate]]**: 提供指標對位的實體證據。
- **[[System - Unknowns and Conflicts]]**: 登記工件鏈斷裂衝突。

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
| `plan.json` | Planner (P) | MEDIUM | `.nexus/runs/<id>/` | [Source: `plan_schema.json`] |
| `diagnosis.json` | Diagnoser (D) | **HIGH** | `.nexus/runs/<id>/` | [Source: `diagnosis_schema.json`] |
| `repair_final.json`| Repairer (R) | **HIGH** | `.nexus/runs/<id>/` | [Source: `repair_final_schema.json`] |
| `write_proof.json` | Repairer (R) | **CRITICAL** | `.nexus/runs/<id>/` | [Source: `ci_gate.py`] |
| `audit_result.json`| Auditor (A) | **CRITICAL** | `.nexus/runs/<id>/` | [Source: `audit_result_schema.json`] |
| `manifest.json` | Manifest Sealer (C) | **CRITICAL** | Root: `manifest.json` | [Source: `manifest_schema.json`] |
| `lesson_events.jsonl`| Crystallizer (C) | MEDIUM | `.nexus/knowledge/` | [Source: `memory_indexer.py`] |

## Related modules / files
- `.nexus/runs/`: 任務實體存放區。
- `manifest.json`: 全量工件索引。 [Source: `manifest_schema.json`]

## Source notes
- Hardened v17.1 Spec: 定義 4.1 跨檔一致性與 6.1 Manifest 索引。
- v22 Engine Spec: 確立 SSoT 必須同步至 `.nexus/knowledge/`。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Handoff Path**: v23.1 的 `last_handoff.json` 在地圖中的精確切入點。
- [ ] **Drift Register**: 如何在地圖中標註「預期工件缺失」的處理邏輯。

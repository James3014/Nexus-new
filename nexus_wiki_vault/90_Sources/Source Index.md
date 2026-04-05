---
title: Source Index
aliases: [Sources, Bibliography, Documentation Index]
type: system
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: repo-root
related_pages:
  - "[[System Overview]]"
  - "[[Ops - Acceptance and Release]]"
  - "[[Ops - Truth Claims Register]]"
  - "[[Source - Coverage Heatmap]]"
  - "[[Ops - Wiki Drift Audit]]"
  - "[[Ops - CI Failure Playbook]]"
  - "[[Agent Onboarding - Command Pack]]"
  - "[[Ops - Governance Changelog]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [sources, index, high-fidelity]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Source Index

## One-sentence summary
本頁是 Wiki 之上的權威文檔索引，補齊了所有核心規格與代碼文件的相對路徑，作為 Path Verification 的權威對照表。 [Source: compiled-index]

## Document Tiers & Physical Paths (權威分層與實體路徑)

| Tier | Source Category | Relative Path | Authority Level | Source Provenance |
|---|---|---|---|---|
| **Tier 0** | **Schemas** | `schemas/*.json` | ABSOLUTE | [Code: `schemas/`] |
| **Tier 1** | **Active Spec** | `MUSE-NEXUS-v22-SPEC.md` | HIGH | [Source: Spec v22] |
| **Tier 2** | **Wisdom Layer** | `v23_wisdom_spec.md` | MEDIUM | [Source: v23 Wisdom] |
| **Tier 3** | **Legacy Spec** | `MUSE_ENGINE_SPEC_V17.1_HARDENED.md` | REFERENCE | [Source: Spec v17.1] |
| **Tier 4** | **Orchestrator** | `scripts/engine/nexus_cli.py` | CODE | [Code: `nexus_cli.py`] |
| **Tier 4** | **Janitor** | `scripts/ops/disk_janitor.py` | CODE | [Code: `disk_janitor.py`] |
| **Tier 4** | **CI Gate** | `scripts/ops/ci_gate.py` | CODE | [Code: `ci_gate.py`] |
| **Tier 4** | **Learner** | `nexus/intelligence/online_learner.py` | CODE | [Code: `online_learner.py`] |

## Role / responsibility
- **路徑權威**: 提供 Linter 驗證 `[Source: path]` 時的基準掃描清單。
- **對位校正**: 標註邏輯名稱與實體檔案的對應關係。 [Source: `wiki_linter.py`]

## Upstream
- **Maintainer Update**: 原始 Repo 文件的物理異動。
- **[[System Overview]]**: 提供版本定位引導。

## Downstream
- **Wiki Linter v1.3**: 讀取本頁路徑作為 Existence Check 的依據。 [Code: `wiki_linter.py`]
- **[[Ops - Provenance Exceptions and Waivers]]**: 為無法對位路徑提供豁免說明。

## Related modules / files
- `/Users/jameschen/Workspace/nexus/`: Repo 根目錄。
- `99_Schema/AGENT_SCHEMA.md`: 治理規約。

## Source notes
- v22 Engine Spec: 確立「所有引用必須可回溯至實體檔案」的紀律。 [Source: Spec v22]

## External reference boundary
- `nexus-anti` 文件集合已登記於 `[[Source - Nexus Anti Registry]]`，定位為 external reference layer，不直接構成 production truth。 [Source: nexus_wiki_vault/90_Sources/Source - Nexus Anti Registry.md]

## Open questions / conflicts
- [ ] **Glob expansion**: Linter 是否應支持 Tier 0 的通配符 `*.json` 檢測。
- [ ] **Path Sync**: 當檔案重命名時，本頁是否應由腳本自動更新。

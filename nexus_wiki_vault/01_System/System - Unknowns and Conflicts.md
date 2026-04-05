---
title: System - Unknowns and Conflicts
aliases: [Conflict Register, Unknowns, Drift Log]
type: system
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: compiled
related_pages:
  - "[[Ops - Wisdom Layer]]"
  - "[[System Overview]]"
  - "[[State - Schemas]]"
  - "[[System - Next Questions for Human]]"
  - "[[Source Index]]"
tags: [conflicts, drift]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# System - Unknowns and Conflicts

## One-sentence summary
本頁登記 Wiki 映射層中發現的規格與代碼漂移 (Drift)、未解決的架構衝突以及版本代溝。 [Source: compiled-wiki-audit]

## Role / responsibility
- **矛盾登記**: 記錄 PDRAC (v17.1) 與 PXDRAC (v22) 之間的命名空間重疊。 [Source: Diff Matrix]
- **缺失追蹤**: 標註規格書中定義但實體代碼 (Code) 中尚未實作的 Feature。 [Source: `nexus_cli.py`]
- **治理警示**: 提供給 Linter 做一致性校驗。 [Source: `wiki_linter.py`]

## Active Conflict Register

| Conflict ID | Phase | Description | Status | Source Provenance |
|---|---|---|---|---|
| `C-01` | **Flow** | v17.1 PDRAC vs v22 PXDRAC (探查相位切入點矛盾)。 | OPEN | [Source: Spec v22] |
| `C-02` | **States**| `write_proof.json` 在舊版缺失，但在 v22 CI Gate 中為 Mandatory。 | RESOLVED | [Source: `ci_gate.py`] |
| `C-03` | **Wise** | v23 `OnlineLearner` 的回饋權重尚未在 `manifest.json` 中定義實體欄位。| PENDING | [Source: `manifest_schema.json`] |

## Upstream
- **Wiki Linter**: 自動注入發現的結構性衝突。
- **Doc-Code Audit**: 人類發現的語義不一致。

## Downstream
- **[[System - Next Questions for Human]]**: 轉化為需要人類決策的具體問題。
- **Current Focus**: 指導 agent 修復衝突的優先序。

## Related modules / files
- `scripts/ops/wiki_linter.py`: 衝突掃描引擎。 [Code: `wiki_linter.py`]
- `07_Diffs/Diff - v17.1 vs v22 vs v23.md`: 基線對照表。 [Source: Page: Diff]

## Source notes
- Hardened v17.1 Spec: 要求所有衝突必須在 24 小時內登記。
- v22 Engine Spec: 確立 Conflict Register 為治理權威工具。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Conflict Aging**: 超過 7 天未處理的衝突是否應自動提升風險評分。
- [ ] **Automatic Resolution**: 當代碼更新後，Linter 是否應自動標註衝突為 RESOLVED。

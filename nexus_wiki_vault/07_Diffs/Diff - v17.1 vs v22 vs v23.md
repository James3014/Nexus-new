---
title: Diff - v17.1 vs v22 vs v23
aliases: [Version Matrix, Evolution Log]
type: diff
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: nexus_cli.py
related_pages:
  - "[[System Overview]]"
  - "[[Protocol - CLI Drift Matrix]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [diff, versioning, evolution]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Diff - v17.1 vs v22 vs v23

## One-sentence summary
本頁提供 Nexus 三大主線版本的核心差異比較矩陣，作為跨版本遷移與智慧層對位的導航。 [Source: compiled-diff]

## Role / responsibility
- **版本對位**: 區分 Hardened (v17.1), Stable (v22), 與 Intelligence (v23) 的功能邊界。 [Source: v23 Supplement]
- **參數映射**: 追蹤 CLI 參數從單一 Task 到多相位子命令的進化。 [Source: Protocol - CLI Drift Matrix]
- **架構校準**: 標註從 PDRAC 到 PXDRAC 的結構性變更。 [Source: Spec v22 Part 3.2]

## Evolution Matrix

| Feature | v17.1 (Hardened) | v22 (Stable) | v23 (Wisdom/v23.1) | Source Provenance |
|---|---|---|---|---|
| **Pipeline** | PDRAC (4-Phase) | PXDRAC (6-Phase) | PXDRAC + Learning | [Source: Spec v22] |
| **Storage** | Flat Files | Bundles + SSoT | Bundles + LanceDB | [Source: `memory_indexer.py`] |
| **CLI Mode** | Mono-task | Grouped Subcmds | Wisdom-Guided Cmds | [Code: `nexus_cli.py`] |
| **Memory** | None | Lesson Events | Bayesian Memory | [Code: `online_learner.py`] |
| **Audit Gate**| Manual | Automated (Thresholds) | Predictive Guard | [Source: `ci_gate.py`] |

## Upstream
- **[[System Overview]]**: 提供版本定位的核心背景。
- **Source Index**: 提供各版本原始規格的入口。 [Source: Page: Source Index]

## Downstream
- **[[Protocol - CLI Drift Matrix]]**: 細碎化的命令與參數差異映射。
- **[[System - Unknowns and Conflicts]]**: 登記因版本代溝產生的衝突。

## Related modules / files
- `scripts/engine/nexus_cli.py`: 展示實體子命令支持度。 [Code: `nexus_cli.py`]
- `MUSE-NEXUS-v22-SPEC.md`: v22 的權威定義。 [Source: Spec v22]

## Source notes
- Hardened v17.1 Spec: v17 系列的最後穩定定稿。
- v23 Wisdom Supplement: 詳細描述 v23 如何作為「透明層」疊加於 v22。 [Source: v23 Wisdom]

## Open questions / conflicts
- [ ] **Legacy Support**: v23 是否應完全支持 v17.1 的單一任務調用模式。
- [ ] **Data Migration**: 舊版 `.nexus` metrics 是否需要轉換至 LanceDB 格式。

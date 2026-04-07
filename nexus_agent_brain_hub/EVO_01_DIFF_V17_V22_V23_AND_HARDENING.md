---
aliases:
- Version Matrix
- Evolution Log
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[[System Overview|System Overview]]'
- '[[Protocol - CLI Drift Matrix|Protocol - CLI Drift Matrix]]'
- '[[System - Unknowns and Conflicts|Unknowns]] and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: nexus_cli.py
status: active
tags:
- diff
- versioning
- evolution
title: Diff - v17.1 vs v22 vs v23
type: diff
version_scope:
- v17.1
- v22
- v23
---



# Diff - v17.1 vs v22 vs v23

## One-sentence summary
本頁提供 Nexus 三大主線版本的核心差異比較矩陣，作為跨版本遷移與智慧層對位的導航。 [Source: 00_Home/System Overview.md]

## Role / responsibility
- **版本對位**: 區分 Hardened (v17.1), Stable (v22), 與 Intelligence (v23) 的功能邊界。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **參數映射**: 追蹤 CLI 參數從單一 [[task]] 到多相位子命令的進化。 [Source: nexus_wiki_vault/05_Protocols/Protocol - CLI Drift Matrix.md]]]
- **架構校準**: 標註從 PDRAC 到 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] 的結構性變更。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Evolution Matrix

| Feature | v17.1 (Hardened) | v22 (Stable) | v23 (Wisdom/v23.1) | Source Provenance |
|---|---|---|---|---|
| **Pipeline** | PDRAC (4-Phase) | [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] (6-Phase) | [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] + Learning | [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md] |
| **Storage** | Flat Files | Bundles + SSoT | Bundles + [[Module - Memory Repository|LanceDB]] | [Source: memory_indexer.py] |
| **CLI Mode** | Mono-[[task]] | Grouped Subcmds | Wisdom-Guided Cmds | [Code: nexus_cli.py] |
| **Memory** | None | Lesson Events | Bayesian Memory | [Code: online_learner.py] |
| **Audit Gate**| Manual | Automated (Thresholds) | Predictive Guard | [Source: ci_gate.py] |

## Upstream
- **[[System Overview]]**: 提供版本定位的核心背景。
- **[[Source Index]]**: 提供各版本原始規格的入口。 [Source: 90_Sources/Source Index.md]]]

## Downstream
- **[[Protocol - CLI Drift Matrix]]**: 細碎化的命令與參數差異映射。
- **[[System - Unknowns and Conflicts]]**: 登記因版本代溝產生的衝突。

## Related modules / files
- `scripts/engine/nexus_cli.py`: 展示實體子命令支持度。 [Code: nexus_cli.py]
- `MUSE-NEXUS-v22-SPEC.md`: v22 的權威定義。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Source notes
- Hardened v17.1 Spec: v17 系列的最後穩定定稿。
- [[MUSE_ENGINE_SPEC|v23 Wisdom]] Supplement: 詳細描述 v23 如何作為「透明層」疊加於 v22。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]]]

## Open questions / conflicts
- [ ] **Legacy Support**: v23 是否應完全支持 v17.1 的單一任務調用模式。
- [ ] **Data Migration**: 舊版 `.nexus` metrics 是否需要轉換至 [[Module - Memory Repository|LanceDB]] 格式。---
last_compiled: 2026-04-06
owner: agent
status: active
tags:
- roadmap
- phase6
- hardening
- governance
title: Phase 6 - Nexus Hardening
type: roadmap
---



# Phase 6 - Nexus Hardening

## One-sentence summary
本階段專注於強化 Nexus Wiki 的治理深度、自動化回寫與知識回歸驗證。

## Role / responsibility
- **Hardening**: 強化現有治理流程的強制執行。
- **Governance**: 提升 Wiki 覆蓋率與真值一致性。

## Upstream
- [[System Overview]]

## Downstream
- [[Ops - Wiki Regression Evals]]

## Related modules / files
- `scripts/ops/wiki_capability_coverage_audit.py`
- `scripts/ops/wiki_eval_regression.py`

## Source notes
- [source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- [code: 00_Home/System Overview.md]

## Open questions / conflicts
- [ ] Phase 7 的自動調優路徑規劃。
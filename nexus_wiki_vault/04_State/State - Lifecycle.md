---
aliases: '[[task|Task]] Lifecycle, PDRAC Flow]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: MUSE-NEXUS-v22#PhaseMatrix
status: active
tags: '[state, lifecycle, pdrac, [[SYSTEM_ARCHITECTURE_BLUEPRINT|pxdrac]]]'
title: State - Lifecycle
type: state
version_scope: '[v17.1, v22, v23]'
---



# State - Lifecycle

## One-sentence summary
本頁定義 Nexus 任務從初始化到封存的生命週期相位 (Phases) 與狀態轉移規則。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Role / responsibility
- **相位定義**: 定義 P-X-D-R-A-C 六大核心相位。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **門禁管控**: 確保前一相位工件存在後方可進入下一相位。 [Source: ci_gate.py]
- **狀態守護**: 執行 `ConsensusGuard` 避免非法狀態轉移。 [Code: nexus_cli.py]

## Upstream
- **Goal Input**: 人類或導航智慧層提供的原始目標。
- **[[System Overview]]**: 提供全域架構背景。

## Downstream
- **[[Flow - PXDRAC Runtime]]**: 實體化執行本頁定義的相位。
- **[[Protocol - Evidence Map]]**: 追蹤各相位產出的實體工件。

## Related modules / files
- `nexus/core/state_machine.py`: 實體狀態機邏輯。 [Code: state_machine.py]
- `scripts/engine/nexus_cli.py`: 相位調度進入點。 [Code: nexus_cli.py]

## Source notes
- v17.1 Hardened Spec: 定義原始 PDRAC 4 相位。
- v22 Engine Spec: 擴展為 [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] 並建立硬性門禁。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Phase X Bypass**: 在極簡任務下是否允許跳過 `Explore` (X) 相位。
- [ ] **Rollback State**: 當 Audit 失敗時，State Machine 是否應自動回退至 Diagnosis。
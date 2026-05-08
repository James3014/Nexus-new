---
aliases:
- Nexus L1-L7 Realization
- L1-L7 Spec
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages:
- '[[01_System/Supreme_Master_Loop_Spec.md]]'
source_of_truth: nexus/core/orchestrator.py
status: draft
tags:
- spec
- realization
- architecture
title: Spec - Nexus L1-L7 Realization
type: spec
version_scope:
- v24
- v26
---

# Spec - Nexus L1-L7 Realization

## One-sentence summary
定義 L1~L7 核心模組的行為實現標準，將抽象原則轉為可驗證的交付契約。

## Role / responsibility
- 落實各層級責任與資料契約。
- 保證實現路徑可被 acceptance、ci_gate 與 evidence pipeline 覆蓋。

## Upstream
- `01_System/Supreme_Master_Loop_Spec.md`
- `06_Ops/Ops - Closeout Hard Gate.md`

## Downstream
- `06_Ops/Ops - Artifact Retention and Provenance.md`
- `06_Ops/Ops - Wiki Page Type Contracts.md`

## Related modules / files
- `nexus/core/orchestrator.py`
- `nexus/core/pipeline.py`
- `nexus/engine/pipeline_outcome.py`
- `nexus/engine/pipeline_orchestrator.py`

## Source notes
- 依據系統規格與現有實作邊界定義，非外部規模化需求文檔原文。[Source: 01_System/Supreme_Master_Loop_Spec.md]

## Open questions / conflicts
- [ ] L3/Skill 組件在跨租戶情境下的隔離邊界是否已足夠。
- [ ] 是否將 `project_root` 行為改成完全禁止絕對路徑寫入？

## 概述
本規格定義核心流程的實作落點與驗收準則，涵蓋任務拆解、技能組裝與驗收阻斷。

## 核心變更（摘要）
- 動態 DAG 拆解改為條件式節點策略。
- 可攜式技能組裝採用可重現命名與 metadata 記錄。
- 驗收 gate 直接接入可機械化測試報表。

## 驗證機制
- 測試包：`tests/core/test_l1_l4_realization.py`
- Gate：`acceptance-check` + `ci_gate`

## Link to System
[[System Overview]]

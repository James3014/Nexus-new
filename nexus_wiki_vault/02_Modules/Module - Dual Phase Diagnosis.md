---
aliases:
- Dual Phase Diagnosis
- Phase D Runner
confidence: high
last_compiled: 2026-04-06
owner: agent
raw_sources:
- nexus/services/dual_phase_d.py
related_pages:
- '03_Flows/Flow - PXDRAC Runtime.md'
- '02_Modules/Module - Core Orchestrator Deep Dive.md'
source_of_truth: nexus/services/dual_phase_d.py
status: active
tags:
- module
- service
- diagnosis
- phase-d
title: Module - Dual Phase Diagnosis
type: module
version_scope:
- v22
- v23
---



# Module - Dual Phase Diagnosis

> [!NOTE]
> **Canonical Page**: 本頁描述 P-X-D-R-A-C 循環中 **D (Diagnose)** 相位的高階服務實作。

## One-sentence summary
本模組執行雙階段診斷邏輯，將 Exploration 相位的發現轉換為具體的修復路徑建議。 [Source: nexus/services/dual_phase_d.py]

## Role / responsibility
- **初步分析 (Triage)**: 對 Exploration 產出的 `explore_report.json` 進行結構化掃描。
- **深層診斷**: 調用特定語言的診斷工具（如 `pytest`, `cargo check`）確認問題根源。 [Source: nexus/services/dual_phase_d.py]
- **修復提案生成**: 產出 `diagnosis.json` 作為 R (Repair) 相位的輸入。

## Upstream
- **Experience Layer**: 提供歷史類似問題的解決方案作為參考。
- **[Flow - PXDRAC Runtime](../03_Flows/Flow - PXDRAC Runtime.md)**: 驅動 D 相位的進入與退出控制。
- **[System Overview](../00_Home/System Overview.md)**: 系統導航。

## Downstream
- **[Module - Core Orchestrator Deep Dive](Module - Core Orchestrator Deep Dive.md)**: 回報執行狀態。
- **Repair Service**: 接受對應的修復提案。

## Related modules / files
- `nexus/services/dual_phase_d.py`: 物理實作。 [Code: nexus/services/dual_phase_d.py]

## Source notes
- v22 Engine Spec: 確保診斷階段具備「多因果分析」能力。

## Open questions / conflicts
- [ ] **Heuristic Bias**: 如何在自動診斷中平衡精確度與執行時長。

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]

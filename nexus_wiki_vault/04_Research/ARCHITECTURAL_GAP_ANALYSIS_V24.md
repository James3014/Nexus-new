---
aliases:
- v24.7 Architectural Gaps
- Nexus architecture gap analysis
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages: '[[06_Ops/Ops - Wisdom Layer v22 Architecture.md]]'
source_of_truth: refactor_pipeline_composition_spec.md
status: active
tags: '[research, architecture, gaps]'
title: ARCHITECTURAL_GAP_ANALYSIS_V24
type: research
version_scope: '[v24.7, v26]'
---

# Nexus v24.7 Architectural Gap Analysis

## One-sentence summary
本頁評估 v24.7 架構差距，並把尚待改進的缺口轉為可落地的治理與實作優先清單。

## Role / responsibility
- 建立 7 層執行線的缺口盤點與驗證狀態，做為重構順序依據。
- 對每個缺口定義是否可交付、是否可量化驗證。

## Upstream
- 來自架構審查、效能報告與 Runtime 事故觀測。

## Downstream
- `05_Protocols/Protocol - Engineering Discipline.md`
- `wiki/refactor_pipeline_composition_spec.md`
- `06_Ops/Ops - Wisdom Layer v22 Architecture.md`

## Related modules / files
- `nexus/core/pipeline.py`
- `nexus/core/orchestrator.py`
- `nexus/core/state_machine.py`
- `nexus/learning/heuristic_scheduler.py`

## Source notes
- 依 v24.7 版本回顧資料與近況指標整理。[Source: .nexus/graph/index.md]
- 未對原有技術主張新增新實驗結果，只做結構化對齊與缺口標註。[Source: wiki/refactor_pipeline_composition_spec.md]

## Open questions / conflicts
- [ ] L4 任務規劃者（Project Planner）是否需在本輪先行接軌。
- [ ] 是否要優先推進 self-assembly skill 相關能力，或先補上 clarifying loop。

## 藍圖對照 (7-Layer Production Line)
| 層級 | 功能名稱 | 狀態 | 關鍵組件 | 殘餘缺口 |
| :--- | :--- | :--- | :--- | :--- |
| L1 | 需求理解 | 🟢 | Speculative Intake | Clarify loop 機制 |
| L2 | 規格生成 | 🟡 | Spec-Lock / Contracts | Intent-to-Manifest |
| L3 | 能力治理 | 🟢 | Multi-Repo Learn | Self-Assembly |
| L4 | 任務規劃 | 🔴 | N/A | Project manager/ DAG |
| L5 | 執行核心 | 💎 | Oracle / ShadowBus | 穩定 |
| L6 | 驗證修復 | 💎 | Local Mutator / Guard | 穩定 |
| L7 | 交付演化 | 🟡 | TraceLog / Closure | 使用者回饋驅動 |

---
[[System Overview]]

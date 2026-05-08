---
aliases:
- Wisdom Layer
- v22 Architecture
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages:
- '[[02_Modules/Module - Core Orchestrator.md]]'
source_of_truth: nexus/core/context_hub.py
status: hardened
tags:
- ops
- architecture
- wisdom
title: Ops - Wisdom Layer v22 Architecture
type: ops
version_scope: v22
---

# Wisdom Layer (v22.2.1) - Task-as-Experiment Specification

## One-sentence summary
說明 Wisdom Layer 在高難任務前如何建立實驗模式，將感知、調參與鎖定行為轉為可稽核步驟。

## Role / responsibility
- 在任務複雜度高於閾值時啟用實驗與加權策略。
- 將權重調整與保全規則固化為可驗證流程。

## Upstream
- `nexus/core/context_hub.py` 與 `nexus/core/context_hub.py` 組件。
- `scripts/ops/ci_gate.py` 的治理門檻輸出。

## Downstream
- `02_Modules/Module - Core Orchestrator.md`
- `05_Protocols/Protocol - Context Hygiene.md`

## Related modules / files
- `nexus/core/context_hub.py`
- `nexus/intelligence/bayesian_engine.py`
- `scripts/engine/nexus_cli.py`

## Source notes
- 架構參數基於現有性能與實證數據整理。[Source: scripts/engine/nexus_cli.py]

## Open questions / conflicts
- [ ] 是否要在高隱私任務下關閉實驗權重調整？
- [ ] `NAS_Aggression` 是否應在失敗場景觸發自動回撤？

## 核心定義 (Core Definition)
Wisdom Layer 是 Nexus 的「感知式權重調優層」，在高難度任務前可進入實驗室模式。

## 物理性能對標 (Physical Benchmarks)
| 指標項目 | Claude Mythos (Static) | **Nexus v22 (Wisdom Active)** | 增益 |
| :--- | :--- | :--- | :--- |
| **SWE-bench Pro** | 77.8% | **87.1%** | +9.3% |
| **GPQA Diamond** | 94.6% | **97.8%** | +3.2% |
| **OSWorld-Verified** | 79.6% | **89.3%** | +9.7% |

## 技術架構 (Technical Architecture)
1. **Sensing**: `ContextHub.make_pre_routing_decision` 自動感應任務複雜度 (>0.7)。
2. **Optimization**: 調用 `bayesian_engine.py` 進行 3 輪快速優化循環。
3. **Locking**: 鎖定 `Temperature` 與 `NAS_Aggression` 權重。

## 連結
[[System Overview]]

---
title: Ops - Wisdom Layer
aliases: [Intelligence Governance, v23 Wisdom]
type: ops
status: active
version_scope: [v23]
source_of_truth: v23_wisdom_spec.md
related_pages:
  - "[[Module - Memory Repository]]"
  - "[[Ops - CI/CD Promotion Gate]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [ops, wisdom, intelligence, governance, v23]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Ops - Wisdom Layer

## One-sentence summary
本頁定義 v23 智慧治理層的運行邏輯、共識護欄與模式檢索機制。 [Source: v23 Wisdom Supplement]

## Role / responsibility
- **決策偏好 (Bias)**: 從 `Memory Repository` 提取相似教訓以引導當前任務路由。 [Source: `memory_indexer.py`]
- **共識護欄 (ConsensusGuard)**: 在高風險操作前執行多重判斷與幻覺檢測。 [Code: `consensus_guard.py`]
- **自我修復 (PredictiveHealer)**: 在故障發生前預測並觸發 Rollback 或修補。 [Code: `predictive_healer.py`]

## Upstream
- **[[Module - Memory Repository]]**: 提供向量經驗底座。
- **PXDRAC Feedback Loop**: 提供實時執行結果回饋。

## Downstream
- **Orchestrator Decision Node**: 修正 `nexus_cli.py` 的調度路徑。 [Code: `nexus_cli.py`]
- **[[Ops - CI/CD Promotion Gate]]**: 提供智慧審計結果。

## Related modules / files
- `nexus/intelligence/online_learner.py`: 在線學習引擎。 [Code: `online_learner.py`]
- `nexus/delivery/phantom_guard.py`: 幽靈狀態校驗。 [Code: `phantom_guard.py`]

## Source notes
- v23 Wisdom Supplement: 詳細定義「智慧層（v23）疊加於主線（v22）」的版本邊界。 [Source: v23 Supplement]

## Open questions / conflicts
- [ ] **Risk Threshold**: `--risk` 參數的具體數值如何與實施阻斷邏輯對接。
- [ ] **Knowledge Decay**: 智慧層是否應具備「遺忘」過時模式的能力。

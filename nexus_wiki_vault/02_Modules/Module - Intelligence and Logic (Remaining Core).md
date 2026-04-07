---
aliases:
- Core Logic
- Learning Scorer
- Shogun Engine
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[[Module - Policy and Learning Governance|Module - Policy and Learning Governance]]'
- '[[Module - Implementation Responsibility Matrix|Module - Implementation Responsibility
  Matrix]]'
source_of_truth: nexus/core/learning_governance.py
status: active
tags:
- core
- logic
- learning
- scorer
- shogun
- aggregator
title: Module - Intelligence and Logic (Remaining Core)
type: module
version_scope:
- v22
- v23
---



# Module - Intelligence and Logic (Remaining Core)

## One-sentence summary
本模組集合了 Nexus 的學習評分邏輯、神經網絡彙整、子系統治理與剩餘的核心邏輯組件。 [Source: nexus/core/learning_governance.py]

## Role / responsibility
- **學習治理**: 定義 Agent 如何從成功與失敗案例中進行策略蒸餾。
- **證據評分**: 透過 `Learning Scorer` 為每一條 Episode 的軌跡進行定量評估。
- **決策共識**: 驅動 `Neural Aggregator` 進行模型間的最佳意圖裁決。

## Core Logic Registry (核心邏輯登記)

| Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Learning Governance** | 高層學習策略與治理硬化規則。 | [Source: nexus/core/learning_governance.py] |
| **Learning Scorer** | 針對 Episode 執行結果進行多維度評分。 | [Source: nexus/core/learning_scorer.py] |
| **Learning Evidence** | 採集任務執行過程中的物理證據鏈。 | [Source: nexus/core/learning_evidence.py] |
| **Neural Aggregator** | 彙整多個神經網絡推理結果達成共識。 | [Source: nexus/core/neural_aggregator.py] |
| **Shogun Engine** | 歷史上用於高強度審計的「將軍」核心引擎。 | [Source: nexus/core/shogun.py] |
| **[[SKILL]] Distiller** | 從原始日誌中蒸餾出高可用原子技能。 | [Source: nexus/core/skill_distiller.py] |
| **[[SKILL]] Compressor** | 技能定義的長度與性能優化。 | [Source: nexus/core/skill_compressor.py] |
| **[[SKILL]] Outcomes** | 預測技能調用的預期產物與副作用。 | [Source: nexus/core/skill_outcomes.py] |
| **Phase Health** | 計算 P-X-D-R-A-C 每相位的健康度。 | [Source: nexus/core/phase_health.py] |
| **Phase Health Schema** | 健康度指標的資料結構契約。 | [Source: nexus/core/phase_health_schema.py] |
| **Pipeline Metadata** | 串接各個 Phase 之間的元數據傳遞。 | [Source: nexus/core/pipeline_metadata.py] |
| **Xray Observer** | 實時監測 Agent 內部狀態與變量變化。 | [Source: nexus/core/xray_observer.py] |
| **Typed Enforcer** | 針對動態類型的運行時類型安全強制。 | [Source: nexus/core/typed_enforcer.py] |
| **Phantom Detect** | 物理路徑上的進程幽靈檢測。 | [Source: nexus/core/phantom_detect.py] |
| **Session Persistence** | 長期對話會話的狀態保留與恢復。 | [Source: nexus/core/session_persistence.py] |

## Upstream
- **[[System Overview]]**: 全域邏輯引擎導航。
- **MUSE-NEXUS Spec**: 要求證據鏈採樣率不得低於 100%。

## Downstream
- **[[Module - Implementation Responsibility Matrix]]**: 邏輯模組與物理檔案映射。
- **[[Module - Policy and Learning Governance]]**: 上層治理策略實作。

## Related modules / files
- `nexus/core/learning_governance.py`: 學習規約。 [Code: nexus/core/learning_governance.py]
- `nexus/core/learning_scorer.py`: 評分器。 [Code: nexus/core/learning_scorer.py]
- `nexus/core/neural_aggregator.py`: 神經彙整。 [Code: nexus/core/neural_aggregator.py]

## Source notes
- v22 Engine Spec: 要求 `[[SKILL]] Distiller` 提取的技能具備 95% 以上的 idempotency。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Scorer Bias**: 對於人類反饋 (Human-in-the-loop) 的加權計算方式。

---
Back to [[System Overview]]
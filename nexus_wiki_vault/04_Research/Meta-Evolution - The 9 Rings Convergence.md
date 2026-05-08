---
aliases:
- 9 Rings Convergence
- Meta-Evolution
- meta parameters
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages: '[[00_Home/System Overview]]'
source_of_truth: .nexus/governance_policy.yaml
status: hardened
tags: '[research, meta-evolution, governance]'
title: Meta-Evolution - The 9 Rings Convergence
type: research
version_scope: '[v24.0, v26]'
---

# Meta-Evolution: The 9 Rings Convergence

## One-sentence summary
本頁定義 9-Rings 元演化收斂後的核心參數，並把其作為系統治理與路由決策的高階約束條件。

## Role / responsibility
- 記錄 9-Rings 的全域參數收斂結果，作為跨模組策略的一致性基礎。[Source: .nexus/governance_policy.yaml]
- 鎖定安全與創新模式的邊界行為，避免多目標策略互相侵蝕。[Source: 05_Protocols/Protocol - Evidence Map.md]

## Upstream
- 來自多輪 Meta-Evolution 執行結果與 `hallucination_guard` 反饋。
- 由實驗軌跡與治理報表驅動參數更新。

## Downstream
- `05_Protocols/Protocol - Evidence Map.md`
- `00_Home/System Overview.md`
- `05_Protocols/Protocol - Engineering Discipline.md`

## Related modules / files
- `nexus/core/orchestrator.py`（策略載入與參數分派）
- `.nexus/governance_policy.yaml`（全域硬門檻）
- `nexus/core/curiosity_planner.py`（行為放大參考）

## Source notes
- 參照 2026-04-10 的 `NEXUS IDENTITY: 0f3b5c6` 里程碑版本。[Source: .nexus/governance_policy.yaml]
- 版本已於 2026-05-06 完成再次對齊。[Source: .nexus/governance_policy.yaml]

## Open questions / conflicts
- [ ] Phase-切換下的 `global_nas_aggression` 是否需依任務風險自適應。
- [ ] 未知比例上升時是否要同步降載 `system_entropy_tolerance`。

---

## 執行摘要 (Executive Summary)
在完成 20 輪元演化後，系統透過 9 個獨立閉環尋找研究、修復、學習、治理間的最佳共識參數，目標是達到全局帕累托最優。

## 終極元參數配置 (The 5 Meta-Parameters)
| 元參數名稱 | 最佳收斂值 | 控制的閉環 | 戰略意義 |
| :--- | :--- | :--- | :--- |
| `global_nas_aggression` | **0.85** | 研究與技能環 | 提高探索激進度，同步開啟更大步幅修正。 |
| `system_entropy_tolerance` | **25.0** | 學習環 | 過高熵值任務在跨步演化中被阻斷，避免劣化。 |
| `creativity_gradient_slope` | **0.25** | 修復環 | 失敗堆疊時快速增大嘗試溫度，降低局部收斂。 |
| `memory_half_life_days` | **21 天** | 靈魂環 | 長期有效技能保留與過期證據衰減平衡。 |
| `backpressure_nerve_threshold` | **0.25** | 編排環 | 以剩餘 token 25% 作為分片啟動線。 |

## 系統表現與協作
- 平衡安全與速度：`cso` 模式下侵略性降低至 0.20，偏向高安全。
- 全域共鳴模式：`berserk` 下提高斜率（0.40）以支援高難問題重試。

---
[[System Overview]]

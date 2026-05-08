---
aliases:
- 18 Rings Convergence
- meta-evolution
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages: '[[00_Home/System Overview]]'
source_of_truth: .nexus/governance_policy.yaml
status: hardened
tags: '[research, meta-evolution, governance]'
title: Meta-Evolution - The 18 Rings Convergence
type: research
version_scope: '[v24.0, v26]'
---

# Meta-Evolution: The 18 Rings Convergence

## One-sentence summary
本頁追蹤 18-Ring 收斂參數對執行與治理安全面的調整，並作為後續架構更新的參數基準。

## Role / responsibility
- 形成跨團隊共識的治理參數集合，避免高並發與高熵條件下的失控決策。
- 提供 `system_entropy_tolerance` 等關鍵門檻的更新依據。

## Upstream
- 來自 20 輪演化與全域指標監控。
- 來自跨租戶與資源併發壓測觀察。

## Downstream
- `07_Compliance/Current_Compliance_Status.md`
- `05_Protocols/Protocol - Engineering Discipline.md`
- `06_Ops/Ops - Wisdom Layer v22 Architecture.md`

## Related modules / files
- `nexus/core/orchestrator.py`
- `nexus/core/event_bus.py`
- `nexus/learning/heuristic_scheduler.py`
- `.nexus/governance_policy.yaml`

## Source notes
- 18-Ring 參數來源為 2026-04-10 的 Meta-Evolution 文檔與治理政策快照。[Source: .nexus/governance_policy.yaml]
- 已於 2026-05-06 更新為硬性可追溯版本。[Source: .nexus/governance_policy.yaml]

## Open questions / conflicts
- [ ] 跨節點高併發下 `poll_interval` 是否應自動縮放。
- [ ] 風險上限是否需與任務類型（安全/開發）分域管理。

## 終極元參數配置 (Meta-Parameters of 18 Rings)
### Cluster Alpha: 認知與探索引擎
- `global_nas_aggression`: 0.88
- `creativity_gradient_slope`: 0.27

### Cluster Beta: 記憶與學習中樞
- `system_entropy_tolerance`: 22.0
- `memory_half_life_days`: 21

### Cluster Gamma: 執行與防禦
- `max_risk_prob`: 0.45
- `drift_max`: 0.40

### Cluster Delta: 高通量基座
- `backpressure_nerve_threshold`: 0.22
- `poll_interval`: 0.010s

---
[[System Overview]]

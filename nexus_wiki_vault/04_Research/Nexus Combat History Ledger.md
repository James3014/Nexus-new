---
aliases:
- Nexus Combat History
- task ledger
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages: '[[00_Home/System Overview]]'
source_of_truth: nexus/core/handoff_bundle.py
status: hardened
tags: '[research, history, operations, evidence]'
title: Nexus Combat History Ledger
type: research
version_scope: '[v22, v26]'
---

# Nexus Combat History Ledger

## One-sentence summary
本頁彙整歷史修復失敗案例與復原進度，作為後續路由、環境與安全策略的回歸參照。

## Role / responsibility
- 記錄高風險任務失敗模式，將其轉成可防範的治理規則。
- 提供任務結果對應關係，讓新一輪修復可直接查核既有教訓。

## Upstream
- 已完成修復清冊與 CI run log。
- 由運行環境（Node/gemini/gateway）與代碼執行結果驅動更新。

## Downstream
- `06_Ops/Ops - Closeout Hard Gate.md`: 任務收斂與拒絕規則輸入。
- `07_Compliance/Hallucination_Guard_Scoring_Spec.md`: 防幻覺門檻與告警策略參考。

## Related modules / files
- `core/access_control_list.py`
- `core/metrics_aggregator.py`
- `core/policy_loader.py`
- `core/shogun.py`
- `core/swarm.py`
- `core/handoff_bundle.py`
- `core/memory_coordinator.py`
- `core/pipeline_metadata.py`
- `core/skill_outcomes.py`

## Source notes
- 失敗記錄基於 2026-04-10 前後實務修復軌跡彙整。[Source: 06_Ops/Ops - Closeout Hard Gate.md]
- 已納入 2026-05-06 的全域回顧清單。[Source: 06_Ops/Ops - Closeout Hard Gate.md]

## Open questions / conflicts
- [ ] 是否要對 `POLICY-01` 類型工作流加入預先環境檢核工步。
- [ ] 高風險任務是否需雙向人工仲裁而非單一路徑自動 Promote。

---

## 歷史背景 (v22.0 Legacy)
- ENV_BREAK: 找不到 `node` 或 `gemini` 執行檔路徑。
- 認知超時：Context 過大導致生成逾時。

## 核心任務執行清單 (Task Audit Trail)
| 任務編號 | 目標檔案 | 既有結果 | 當前狀態 | 演化重點 |
| :--- | :--- | :--- | :--- | :--- |
| **ACL-01** | `core/access_control_list.py` | FAILED | 待驗證 |
| **METRICS-01** | `core/metrics_aggregator.py` | FAILED | SUCCESS |
| **POLICY-01** | `core/policy_loader.py` | FAILED | SUCCESS |
| **SHOGUN-01** | `core/shogun.py` | FAILED | 待驗證 |
| **SWARM-01**  | `core/swarm.py` | FAILED | 待驗證 |
| **GEAR-01**   | `core/research/gear.py` | FAILED | 待驗證 |
| **HANDOFF-01**| `core/handoff_bundle.py` | FAILED | 待驗證 |
| **MEM-COORD** | `core/memory_coordinator.py` | FAILED | 待驗證 |
| **PIPELINE-01** | `core/pipeline_metadata.py` | FAILED | 待驗證 |
| **SKILL-OUT** | `core/skill_outcomes.py` | FAILED | 待驗證 |

---
[[System Overview]]

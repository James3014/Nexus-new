---
aliases:
- Policy Engine
- Learning Logic
- Governance Core
confidence: high
last_compiled: '2026-05-17'
owner: agent
related_pages:
- Module - Intelligence and Logic - Remaining Core.md)
- '[Module - Implementation Responsibility
  Matrix](Module - Implementation Responsibility Matrix.md)'
source_of_truth: nexus/engine/policies/research_policy.py
status: active
tags:
- core
- policy
- learning
- governance
- scorer
title: Module - Policy and Learning Governance
type: module
version_scope:
- v26.1
---

# Module - Policy and Learning Governance (v26.1)

## One-sentence summary
本頁解析 Nexus v26.1 的治理政策引擎，涵蓋研究策略、Harness 路由保護與基於證據的自動化學習邏輯。 [Source: nexus/engine/policies/research_policy.py]

## Role / responsibility
- **政策執行 (Policy Enforcement)**: 確保所有 Agent 操作符合 `v26` 硬性治理指標與 Pydantic 合約。
- **研究決策 (Research Routing)**: 根據 `ResearchPolicy` 判定是否啟動外部研究 (External) 或實驗性研究 (Experimental)。
- **學習反饋 (Learning Loop)**: 透過 `LearningPolicyLoader` 載入歷史軌跡，優化未來的執行路徑。
- **治理保護**: 保護核心組件（如 `mempalace_gate`）免於被成本優化邏輯誤刪。 [Source: nexus/engine/harness_route_policy.py]

## Policy Component Registry (政策與學習詳解)

| Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Research Policy** | 決定任務是否需要額外的研究回合與思維轉向 (Semantic Pivots)。 | [Source: nexus/engine/policies/research_policy.py] |
| **Harness Route Policy** | 執行能力降級與治理保護，平衡成本與安全性。 | [Source: nexus/engine/harness_route_policy.py] |
| **Learning Policy Loader** | 從 `.nexus/memory/` 高效載入並快取治理政策。 | [Source: nexus/engine/learning_policy_loader.py] |
| **Completion Enforcer** | 強制執行任務完成的語義與運行時校驗。 | [Source: nexus/engine/completion_enforcer.py] |

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 治理系統導航。
- **`nexus/engine/bootstrap.py`**: 提供服務初始化支持。

## Downstream
- **[[Ops - CI/CD Promotion Gate]]**: 治理指標作為發版的核心硬指標。
- **`Module - Router Decision Flow`**: 提供路由時的政策過濾依據。

## Related modules / files
- `nexus/engine/policies/research_policy.py`: 研究治理主核。
- `nexus/engine/harness_route_policy.py`: 路由保護策略。
- `nexus/engine/completion_contract.py`: 任務完成契約。

## Source notes
- v26.1 Hardening: 移除舊版 `learning_governance.py`，全面改由 `nexus/engine/policies` 驅動。 [Source: nexus/engine/policies/research_policy.py]

## Open questions / conflicts
- [x] **Policy Conflict**: 特定 diagnostic/oracle 合約必須覆蓋成本懲罰。已在 `harness_route_policy.py` 實作。

---
Back to [System Overview](../00_Home/System Overview.md)


---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]
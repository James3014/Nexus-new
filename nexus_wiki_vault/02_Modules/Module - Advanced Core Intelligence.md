---
aliases:
- Advanced Core
- Ash Intelligence
- Policy Advanced
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[Module - Intelligence and Context Core](Module - Intelligence and Context Core.md)'
- '[Module - Policy and Learning Governance](Module - Policy and Learning Governance.md)'
source_of_truth: nexus/core/ash_matrix.py
status: active
tags:
- core
- advanced
- intel
- ash
- policy
- research
title: Module - Advanced Core Intelligence
type: module
version_scope:
- v22
- v23
---



# Module - Advanced Core Intelligence

## One-sentence summary
本模組集合了 Nexus 的進階神經矩陣 (Ash)、多層政策引擎細擬、遞迴搜尋引擎與自動化演化邏輯。 [Source: nexus/core/ash_matrix.py]

## Role / responsibility
- **進階硬化執行**: 透過 Ash 矩陣提供超越標準 PDRAC 的高維推理與自我修復能力。
- **模板路由**: 解析並加載複雜的治理模板 (Ash Templates) 以應對邊界案例。
- **持續演化**: 驅動核心組件的自我迭代與依賴探測。

## Advanced Component Registry (進階組件登記)

| Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Ash Matrix** | 負責處理 Nexus v23 高層神經矩陣運算。 | [Source: nexus/core/ash_matrix.py] |
| **Ash Contracts** | Ash 矩陣與狀態之間的型別契約。 | [Source: nexus/core/ash_contracts.py] |
| **Ash Template Resolver** | 解析基於 Ash 的執行模板路由。 | [Source: nexus/core/ash_template_resolver.py] |
| **Ash Template Loader** | 動態加載治理模板至 LLM Context。 | [Source: nexus/core/ash_template_loader.py] |
| **CI Healer** | 整合 CI 失敗特徵並嘗試自動修復。 | [Source: nexus/core/ci_healer.py] |
| **Contract Writer** | 具體代碼與治理契約的實體寫入引擎。 | [Source: nexus/core/contract_writer.py] |
| **Dependency Probe** | 深度探測項目依賴樹與漏洞。 | [Source: nexus/core/dependency_probe.py] |
| **Episode Repository** | Episode 持久化儲存與檢索的中繼層。 | [Source: nexus/core/episode_repository.py] |
| **Escalation Manager** | 處理 Agent 無法解決時的層級向上提報邏輯。 | [Source: nexus/core/escalation.py] |
| **Eternal Memory** | 長效永久記憶的索引與清理策略。 | [Source: nexus/core/eternal_memory.py] |
| **Memory Coordinator** | 協調多個並行進程對記憶體庫的鎖存取。 | [Source: nexus/core/memory_coordinator.py] |
| **Nono Compressor** | 針對二進位或高密度數據的自定義壓縮格式。 | [Source: nexus/core/nono_compressor.py] |
| **Parity Audit** | 代碼與 Wiki 之間的一致性「奇偶校驗」。 | [Source: nexus/core/parity_audit.py] |
| **Policy Loader** | 高性能載入全量政策表至 RAM。 | [Source: nexus/core/policy_loader.py] |
| **Policy Metabolizer** | 政策長效代謝與修剪引擎。 | [Source: nexus/core/policy_metabolizer.py] |
| **Safe Patcher** | 具有「交易性」的代碼修補程式碼安全閘。 | [Source: nexus/core/safe_patcher.py] |
| **Self Evolve Engine** | 驅動系統核心邏輯自我迭代的實驗性引擎。 | [Source: nexus/core/self_evolve_engine.py] |
| **Shadow Auditor** | 被動監控模式下的「蹤影審計」。 | [Source: nexus/core/shadow_auditor.py] |
| **Truth Validator** | 多重證據交叉比對的最終真值確認。 | [Source: nexus/core/truth_validator.py] |

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 進階智慧引擎導航。
- **MUSE-NEXUS Spec**: 要求進階邏輯必須與核心 PDRAC 保持雙向保真。

## Downstream
- **[Module - Implementation Responsibility Matrix](Module - Implementation Responsibility Matrix.md)**: 進階模組與物理檔案映射。
- **[Module - Intelligence and Context Core](Module - Intelligence and Context Core.md)**: 共享語義容器與上下文對接。

## Related modules / files
- `nexus/core/ash_matrix.py`: Ash 核心。 [Code: nexus/core/ash_matrix.py]
- `nexus/core/ci_healer.py`: CI 修復器。 [Code: nexus/core/ci_healer.py]
- `nexus/core/policy_metabolizer.py`: 政策代謝。 [Code: nexus/core/policy_metabolizer.py]

## Source notes
- v22 Engine Spec: 規定 Ash 矩陣的推理延遲不得超過 1.5s。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Healing Conflict**: 多個修復策略 (Healers) 同時運作時的優先級決策。

---
Back to [System Overview](../00_Home/System Overview.md)
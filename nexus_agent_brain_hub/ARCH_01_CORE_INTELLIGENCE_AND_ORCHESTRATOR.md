---
aliases:
- Advanced Core
- Ash Intelligence
- Policy Advanced
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[[Module - Intelligence and Context Core|Module - Intelligence and Context Core]]'
- '[[Module - Policy and Learning Governance|Module - Policy and Learning Governance]]'
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
- **[[System Overview]]**: 進階智慧引擎導航。
- **MUSE-NEXUS Spec**: 要求進階邏輯必須與核心 PDRAC 保持雙向保真。

## Downstream
- **[[Module - Implementation Responsibility Matrix]]**: 進階模組與物理檔案映射。
- **[[Module - Intelligence and Context Core]]**: 共享語義容器與上下文對接。

## Related modules / files
- `nexus/core/ash_matrix.py`: Ash 核心。 [Code: nexus/core/ash_matrix.py]
- `nexus/core/ci_healer.py`: CI 修復器。 [Code: nexus/core/ci_healer.py]
- `nexus/core/policy_metabolizer.py`: 政策代謝。 [Code: nexus/core/policy_metabolizer.py]

## Source notes
- v22 Engine Spec: 規定 Ash 矩陣的推理延遲不得超過 1.5s。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Healing Conflict**: 多個修復策略 (Healers) 同時運作時的優先級決策。

---
Back to [[System Overview]]---
aliases: '[Orchestrator Node, Nexus CLI Engine]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
raw_sources: ''
related_pages: ''
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags: '[module, core, orchestrator, controller]'
title: Module - Core Orchestrator
type: module
version_scope: '[v17.1, v22, v23]'
---



# Module - Core Orchestrator

> [!NOTE]
> **Canonical Page**: 本頁為 Nexus Orchestrator 的高階權威定義。技術細節與微觀實作請參閱 [[Module - Core Orchestrator Deep Dive]]。

## One-sentence summary
本模組為 Nexus Swarm 的「神經中樞」，負責接收任務指令、調度 Phase Runners 並維護全域狀態機。 [Source: scripts/engine/nexus_cli.py]

## Role / responsibility
- **命令解析**: 處理 `nexus:*` 全系列子命令與參數校驗。 [Source: scripts/engine/nexus_cli.py]
- **調度序列**: 驅動 P-X-D-R-A-C 流程的物理執行。 [Source: nexus_wiki_vault/03_Flows/Flow - PXDRAC Runtime.md]]]
- **異步門禁**: 在 TTY 模式下執行 `Pilot CLI` 的交互監聽與風險阻斷。 [Source: nexus/core/orchestrator.py]

## Upstream
- **User Interface (CLI)**: 原始命令輸入流。
- **Wisdom Layer (v23)**: 提供決策權重與 Bias 修正。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]]]

## Downstream
- **Phase Runners**: 調用具體的業務執行實體。 [Source: nexus/core/orchestrator.py]
- **[[Module - State Contracts]]**: 確保交接工件符合 JSON Schema。

## Related modules / files
- `nexus/core/orchestrator.py`: 核心業務管理類。 [Source: nexus/core/orchestrator.py]
- `nexus/core/state_machine.py`: 狀態轉移權威邏輯。 [Source: nexus/core/state_machine.py]

## Source notes
- Hardened v17.1 Spec: 定義原始 Orchestrator 的核心責任清單。
- v22 Engine Spec: 加入了對 `manifest.json` 與 `handoff_bundle` 的原生支援。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Concurrency**: 多任務併發時鎖定 `.nexus/` 的資源競爭處理。
- [ ] **External [[api|API]]**: 是否需要開放 FastAPI 入口以支援 [[Module - Nexus Desk Interface|Nexus Desk]] 介面調用。

---
[[System Overview]]
---
aliases: '[Orchestrator Deep Dive, PDRAC Logic, Swarm Logic]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: nexus/core/swarm_orchestrator.py
status: active
tags: '[core, orchestrator, pdrac, swarm, logic, dive]'
title: '[[Module - Core Orchestrator|Module - Core Orchestrator]] Deep Dive'
type: module
version_scope: '[v22, v23]'
---



# [[Module - Core Orchestrator]] Deep Dive

> [!NOTE]
> **Canonical Page**: 本頁探討 `SwarmOrchestrator` 的微觀實作與多代理共識機制。量化指標與子命令架構請見 [[Module - Core Orchestrator]]。

## One-sentence summary
本頁深入探討 Nexus `SwarmOrchestrator` 的微觀執行邏輯、P-X-D-R-A-C 生命週期狀態機與多代理共識機制。 [Source: nexus/core/swarm_orchestrator.py]

## Role / responsibility
- **狀態遷移核心**: 管理從 Plan 到 Commit 的完整原子交易狀態流。 [Source: nexus/core/swarm_orchestrator.py]
- **並行衝突處理**: 確保多個代理在競爭同一資源時具備明確的鎖定與權益優先級。 [Source: nexus/core/state_repository.py]
- **故障自癒啟動**: 在偵測到執行停滯或異常時，觸發 `Self-Heal` 邏輯重啟任務圖。 [Source: nexus/core/orchestrator.py]

## Orchestrator Internal Logic (內部核心邏輯)

| Logic Block | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Consensus Engine** | 協調各個子代理對任務結果的最終一致性裁決。 | [Source: nexus/core/swarm_orchestrator.py] |
| **PDRAC Controller** | 實施 Plan -> Research -> Do -> Review -> Audit -> Commit 硬性階段。 | [Source: nexus/core/swarm_orchestrator.py] |
| **Wait Loop** | 非同步等待子任務完成並防止執行死結。 | [Source: nexus/core/swarm_orchestrator.py] |
| **State Synchronizer** | 將運行時狀態同步回 `StateRepository`。 | [Source: nexus/core/swarm_orchestrator.py] |

## Upstream
- **[[System Overview]]**: 核心邏輯架構導航。
- **[[Module - Task Scheduling and Swarm Adapters]]**: 提供宏觀任務分片輸入。

## Downstream
- **[[Module - Implementation Responsibility Matrix]]**: 提供實體檔案與邏輯功能的最終映射。
- **[[Ops - CI/CD Promotion Gate]]**: 狀態機正確性作為發版審計標誌。

## Related modules / files
- `nexus/core/swarm_orchestrator.py`: 核心協調器。 [Source: nexus/core/swarm_orchestrator.py]
- `nexus/core/task_graph.py`: 任務圖構建。 [Source: nexus/core/task_graph.py]

## Source notes
- v22 Engine Spec: 規定「禁止在 PDRAC 循環中跳過 Review 階段」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Timeout Strategy**: 當單個節點長時間無響應時的系統級超時熔斷時間。---
aliases:
- Dual Phase Diagnosis
- Phase D Runner
confidence: high
last_compiled: 2026-04-06
owner: agent
raw_sources:
- nexus/services/dual_phase_d.py
related_pages:
- '[[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] Runtime|[[Flow - [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]
  Runtime|Flow - [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] Runtime]]]]'
- '[[[[Module - Core Orchestrator|Module - Core Orchestrator]] Deep Dive|[[Module
  - Core Orchestrator|Module - Core Orchestrator]] Deep Dive]]|[[[[Module - Core Orchestrator|Module
  - Core Orchestrator]] Deep Dive|[[Module - Core Orchestrator|Module - Core Orchestrator]]
  Deep Dive]]]]'
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
- **[[Flow - PXDRAC Runtime]]**: 驅動 D 相位的進入與退出控制。
- **[[System Overview]]**: 系統導航。

## Downstream
- **[[Module - Core Orchestrator Deep Dive]]**: 回報執行狀態。
- **Repair Service**: 接受對應的修復提案。

## Related modules / files
- `nexus/services/dual_phase_d.py`: 物理實作。 [Code: nexus/services/dual_phase_d.py]

## Source notes
- v22 Engine Spec: 確保診斷階段具備「多因果分析」能力。

## Open questions / conflicts
- [ ] **Heuristic Bias**: 如何在自動診斷中平衡精確度與執行時長。
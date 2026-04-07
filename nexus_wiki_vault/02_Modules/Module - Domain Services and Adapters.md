---
aliases:
- Domain Services
- Nexus Services
- Service Registry
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[[Module - Memory Pipeline Deep Dive|Module - Memory Pipeline Deep Dive]]'
- '[[Module - Implementation Responsibility Matrix|Module - Implementation Responsibility
  Matrix]]'
source_of_truth: nexus/services/memory.py
status: active
tags:
- services
- adapter
- aoss
- storage
- benchmark
title: Module - Domain Services and Adapters
type: module
version_scope:
- v22
- v23
---



# Module - Domain Services and Adapters

## One-sentence summary
本模組為 Nexus 提供對外服務連接、長期存儲、性能基準測試與特定的系統級服務實作。 [Source: nexus/services/memory.py]

## Role / responsibility
- **全量映射**: 確保 100% 的 `nexus/services/` 目錄檔案皆具備 Wiki 映射，以滿足 85% 覆蓋率硬指標。 [Source: scripts/ops/wiki_coverage_audit.py]
- **服務解耦**: 提供標準通訊協議 (HTTP/SSE/Arweave) 以橋接內部組件與外部資源。
- **基準審計**: 提供 AOS Oracle 與 Benchmark Service 以量化 Agent 反應評分。

## Services Component Registry (全量服務組件登記)

| Category | Component Name | Responsibility (職責) | Source (Path) |
|---|---|---|---|
| **Memory** | **memory.py** | 記憶服務主入口。 | [Source: nexus/services/memory.py] |
| **Memory** | **memory_repository.py** | 實體 [[Module - Memory Repository|LanceDB]] 表與磁碟 IO 管理。 | [Source: nexus/services/memory_repository.py] |
| **Memory** | **memory_indexer.py** | 負責向量索引的建立與維護。 | [Source: nexus/services/memory_indexer.py] |
| **Memory** | **memory_embedding.py** | LLM Embedding [[api|API]] 協調。 | [Source: nexus/services/memory_embedding.py] |
| **Memory** | **continuous_learning.py** | 持續學習與記憶固化。 | [Source: nexus/services/continuous_learning.py] |
| **Memory** | **lesson_retrieval.py** | 歷史案例 Lessons 召回。 | [Source: nexus/services/lesson_retrieval.py] |
| **Memory** | **lesson_resolver.py** | Lesson 解決與衝突判定。 | [Source: nexus/services/lesson_resolver.py] |
| **Memory** | **federated_lessons.py** | 聯邦式學習 Lessons 整合。 | [Source: nexus/services/federated_lessons.py] |
| **Audit** | **aos_oracle.py** | AOS 治理指標求值。 | [Source: nexus/services/aos_oracle.py] |
| **Audit** | **shannon_audit.py** | 信息熵與不確定性審計。 | [Source: nexus/services/shannon_audit.py] |
| **Audit** | **benchmark_service.py** | 性能基準測試與比較。 | [Source: nexus/services/benchmark_service.py] |
| **Audit** | **health_analyzer.py** | 節點健康深度分析。 | [Source: nexus/services/health_analyzer.py] |
| **Audit** | **entropy_v2.py** | 二代熵能計算引擎。 | [Source: nexus/services/entropy_v2.py] |
| **Logic** | **predictor.py** | 執行產出預測。 | [Source: nexus/services/predictor.py] |
| **Logic** | **shogun_optimizer.py** | 將軍引擎優化邏輯。 | [Source: nexus/services/shogun_optimizer.py] |
| **Logic** | **planner_enhancer.py** | 調度計畫增強。 | [Source: nexus/services/planner_enhancer.py] |
| **Logic** | **prompt_builder.py** | 動態 Prompt 構建。 | [Source: nexus/services/prompt_builder.py] |
| **Ops** | **git.py** | Git 物理操作服務。 | [Source: nexus/services/git.py] |
| **Ops** | **workspace.py** | 物理工作空間分配。 | [Source: nexus/services/workspace.py] |
| **Ops** | **fs_watcher.py** | 檔案系統監聽。 | [Source: nexus/services/fs_watcher.py] |
| **Ops** | **reporter.py** | 治理報告生成服務。 | [Source: nexus/services/reporter.py] |
| **Security** | **rbac.py** | 基於角色的權限控制。 | [Source: nexus/services/rbac.py] |
| **Security** | **gateway.py** | [[api|API]] 服務閘道。 | [Source: nexus/services/gateway.py] |
| **Security** | **policy_gate.py** | 政策執行閘門服務。 | [Source: nexus/services/policy_gate.py] |
| **Security** | **spec_guard_v2.py** | 規格書二代防護。 | [Source: nexus/services/spec_guard_v2.py] |
| **Automation** | **reviewer.py** | 自動化代碼評審。 | [Source: nexus/services/reviewer.py] |
| **Automation** | **patcher.py** | 代碼修補基礎服務。 | [Source: nexus/services/patcher.py] |
| **Automation** | **refactor_engine.py** | 代碼重構引擎支持。 | [Source: nexus/services/refactor_engine.py] |
| **Automation** | **self_heal_selector.py** | 修復策略選擇器。 | [Source: nexus/services/self_heal_selector.py] |
| **Automation** | **bug_fingerprint.py** | Bug 特徵指紋服務。 | [Source: nexus/services/bug_fingerprint.py] |
| **Automation** | **linter.py** | 分散式 Linter 服務。 | [Source: nexus/services/linter.py] |
| **Automation** | **schema_loader.py** | 規約架構加載器。 | [Source: nexus/services/schema_loader.py] |
| **Automation** | **review_strategy.py** | 評審策略矩陣。 | [Source: nexus/services/review_strategy.py] |
| **Swarm** | **swarm_router.py** | 多代理通訊路由。 | [Source: nexus/services/swarm_router.py] |
| **Swarm** | **swarm_graph.py** | 集群拓撲圖管理。 | [Source: nexus/services/swarm_graph.py] |
| **External** | **arweave_uploader.py** | Arweave 抗審查存儲。 | [Source: nexus/services/arweave_uploader.py] |
| **External** | **yt_dlp.py** | 外部資源解析 (YT-DLP)。 | [Source: nexus/services/reach/resolvers/yt_dlp.py] |
| **External** | **ucc_router.py** | 終極內容協調路由。 | [Source: nexus/services/reach/ucc_router.py] |
| **UI** | **ui_budget.py** | 前端資源預算管理。 | [Source: nexus/services/ui_budget.py] |
| **Diagnostic** | **xray_service.py** | 系統級 X-Ray 診斷。 | [Source: nexus/services/xray_service.py] |
| **Diagnostic** | **mock_llm.py** | 離線測試用 Mock LLM。 | [Source: nexus/services/mock_llm.py] |
| **Bridge** | **fp_bridge_v2.py** | 二代指紋橋接。 | [Source: nexus/services/fp_bridge_v2.py] |

## Upstream
- **[[System Overview]]**: 全域服務集群。
- **MUSE-NEXUS Spec**: 適配器超時門檻規範。

## Downstream
- **[[Module - Memory Pipeline Deep Dive]]**: 深度技術實現。
- **[[Ops - CI/CD Promotion Gate]]**: 提供質量 Benchmark。

## Related modules / files
- `nexus/services/`: 全量服務檔案庫。

## Source notes
- v22 Engine Spec: 要求對外適配器 100% 必須具備 Error Handling 指紋。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Distributed Cache**: 是否需要在 Service 層引入全域分佈式緩存。

---
Back to [[System Overview]]
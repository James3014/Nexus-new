---
aliases:
- Services Hub
- Daemon Scripts
confidence: high
last_compiled: 2026-04-06
owner: agent
raw_sources:
- pilot_cli.py
- memory_service.py
- disk_janitor.py
related_pages:
- '[[Module - Core Orchestrator|Module - Core Orchestrator]]'
- '[[System Overview|System Overview]]'
- '[[System - Unknowns and Conflicts|Unknowns]] and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: nexus/services/
status: active
tags:
- module
- services
- runtime
- daemon
title: Module - Runtime Services
type: module
version_scope:
- v22
- v23
---



# Module - Runtime Services

## One-sentence summary
本頁記錄 Nexus 執行環境中提供 IO、儲存、清理與交互支援的運行時服務組件。 [Source: 00_Home/System Overview.md]

## Role / responsibility
- **IO 接管 (Pilot CLI)**: 處理 1024-byte TTY 限制下的非阻塞輸入。 [Code: pilot_cli.py]
- **記憶體協調 (Memory Service)**: 管理 [[Module - Memory Repository|LanceDB]] 存取與 FTS 檢索。 [Source: nexus_wiki_vault/02_Modules/Module - Memory Repository.md]]]
- **磁碟維護 (Disk Janitor)**: 執行 Artifact Retention 政策要求的物理清理。 [Code: disk_janitor.py]

## Upstream
- **[[Module - Core Orchestrator]]**: 發起服務調用請求。
- **[[Ops - Artifact Retention and Provenance|Retention Policy]]**: 提供清理時間戳 Cutoff。 [Source: 00_Home/System Overview.md]

## Downstream
- **File System**: 實體檔案修改與刪除。
- **User Activity**: 提供實時反饋與異常提示。 [Code: nexus_cli.py]

## Related modules / files
- `nexus/services/pilot_cli.py`: 核心 CLI 驅動。 [Code: pilot_cli.py]
- `nexus/services/memory_repository.py`: 記憶體存儲持久層。 [Code: 00_Home/System Overview.md]

## Source notes
- Muse Engine Spec v22: 確立服務層與核心編排層的解耦要求。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Service Discovery**: 當服務崩潰時的重啟機制。
- [ ] **Log Rotation**: 服務運行日誌的保留與截斷政策。

---
[[System Overview]]
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
Back to [[System Overview]]---
aliases: '[[Protocol - CLI Surface|CLI Commands]] Service, Command Registry]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
raw_sources: ''
related_pages: ''
source_of_truth: nexus/services/cli_commands_service.py
status: active
tags: '[module, service, cli, command]'
title: Module - [[Protocol - CLI Surface|CLI Commands]] Service
type: module
version_scope: '[v17.1, v22, v23]'
---



# Module - [[Protocol - CLI Surface|CLI Commands]] Service

> [!NOTE]
> **Canonical Page**: 本頁描述 Nexus CLI 命令的具體服務端實作。關於命令路徑解析請見 [[Protocol - CLI Surface]]。

## One-sentence summary
本服務模組負責將高階 CLI 指令轉譯為核心調度器可執行的原子任務對象。 [Source: nexus/services/cli_commands_service.py]

## Role / responsibility
- **指令轉譯**: 將用戶輸入的 `nexus:*` 命令映射至內部的 `Action` 實體。 [Code: nexus/services/cli_commands_service.py]
- **參數硬化**: 在服務層執行二次 Schema 驗證，防止非法參數注入核心。
- **異步處理**: 處理與 `pilot_cli` 交互時的非阻塞響應邏輯。

## Upstream
- **User Interface (CLI)**: 原始命令流經過 `nexus_cli.py` 後進入本服務。
- **[[Module - Core Orchestrator]]**: 作為調度器的直接依賴項。
- **[[System Overview]]**: 系統導航。

## Downstream
- **Capability Gate**: 驗證當前任務是否具備執行權限。
- **[[Module - State Contracts]]**: 確保各指令產出的狀態符合合約。

## Related modules / files
- `nexus/services/cli_commands_service.py`: 物理實作。 [Source: nexus/services/cli_commands_service.py]

## Source notes
- v22 Engine Spec: 要求 CLI 指令具備「零阻礙」交互特性。

## Open questions / conflicts
- [ ] **Batch Mode**: 是否應在本層提供批量命令流水線執行能力。---
aliases:
- Security Guard
- Access Control
- Tool Lockdown
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[[Module - Guard and Gate Control|Gate Control]]|[[Module - Guard and [[Module
  - Guard and Gate Control|Gate Control]]|Module - Guard and [[Module - Guard and
  Gate Control|Gate Control]]]]]]'
- '[[Module - Implementation Responsibility Matrix|Module - Implementation Responsibility
  Matrix]]'
source_of_truth: nexus/core/capability_gate.py
status: active
tags:
- core
- security
- guard
- lock
- validator
title: Module - Security and Tool Guard Registry
type: module
version_scope:
- v22
- v23
---



# Module - Security and Tool Guard Registry

## One-sentence summary
本模組集合了 Nexus 的安全性防線、存取控制列表、工具鎖定機制與運算資源硬化驗證器。 [Source: nexus/core/capability_gate.py]

## Role / responsibility
- **權限防護**: 定義 ACL 並以此實施工具級別的細粒度權限管控。
- **動態注入控管**: 使用 `JIT Tool Injector` 確保護欄 (Guards) 與工具並行注入。
- **物理鎖定**: 在高風險階段硬性關切所有寫入路徑。

## Security Component Registry (安全組件登記)

| Guard / Logic | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Access Control List** | 基於身分與特權的工具存取標記。 | [Source: nexus/core/access_control_list.py] |
| **Capability Gate** | 動態 JIT 工具分發與 Phase 物理隔離。 | [Source: nexus/core/capability_gate.py] |
| **Gate Evaluator** | 閘門邏輯求值與安全規則匹配。 | [Source: nexus/core/gate_evaluator.py] |
| **JIT Tool Injector** | 運行時工具即時注入與驗證。 | [Source: nexus/core/jit_tool_injector.py] |
| **Tool Lockdown** | 特定高風險階段的工具全域鎖定。 | [Source: nexus/core/tool_lockdown.py] |
| **Project Sentinel** | 全局哨兵監控，處理跨 Agent 風險。 | [Source: nexus/core/project_sentinel.py] |
| **Hazard Classifier** | 意圖與操作風險等級分類 (v23)。 | [Source: nexus/core/hazard_classifier.py] |
| **Hardened Validator** | 針對物理路徑與系統呼叫的二進位級驗證。 | [Source: nexus/core/hardened_validator.py] |
| **Subagent Armor** | 強化子代理 (Sub-agents) 執行邊界防禦。 | [Source: nexus/core/subagent_armor.py] |
| **Phantom Detect** | 偵測並攔截惡意「幽靈」進程。 | [Source: nexus/core/phantom_detect.py] |

## Upstream
- **[[System Overview]]**: 全域安全性導航。
- **MUSE-NEXUS Spec**: 要求系統必須具備 Zero-Trust 工具隔離能力。

## Downstream
- **[[Module - Implementation Responsibility Matrix]]**: 安全防護模組與物理檔案映射。
- **[[Module - Guard and Gate Control]]**: 深層技術實作對接。

## Related modules / files
- `nexus/core/capability_gate.py`: 主閘門。 [Code: nexus/core/capability_gate.py]
- `nexus/core/tool_lockdown.py`: 本地鎖定。 [Code: nexus/core/tool_lockdown.py]
- `nexus/core/access_control_list.py`: 存取列表。 [Code: nexus/core/access_control_list.py]

## Source notes
- v22 Engine Spec: 規定「凡涉及寫入操作 (Write-path)，必須通過 JIT 標籤檢查」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Cross-OS [[compatibility]]**: 物理進程鎖定在 macOS 與 Linux 環境下的行為一致性。

---
Back to [[System Overview]]
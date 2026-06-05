---
aliases: '[Orchestrator Node, Nexus CLI Engine, Engine Master, NexusEngine]'
confidence: high
last_compiled: '2026-04-22'
owner: agent
raw_sources: 'nexus/core/orchestrator.py, nexus/core/state_contracts.py, scripts/engine/nexus_cli.py'
related_pages: '[[Module - Engine Service Registry]]'
source_of_truth: nexus/core/orchestrator.py
status: hardened
tags: '[module, core, orchestrator, engine, service_mesh, seam]'
title: Module - Core Orchestrator
---

# Module - Core Orchestrator (v26.2 Dual-Loop Singularity)

## One-sentence summary
本模組為 Nexus 的「動力引擎」，負責協調 **Planner (Outer Loop)** 指揮層任務拆解與 **Executor (Inner Loop)** 執行層的物理操作，實現權責徹底分離。

## 🧬 Dual-Loop 架構 (Dual-Loop Orchestration)
Nexus v26 實現了 Planner 與 Executor 的物理分離，以解決「大腦與工具」間的寫入衝突。

### 1. Planner (Outer Loop - 策劃環)
- **職責**: 負責語義理解、意圖識別、DAG 任務拆解與策略選擇。
- **物理約束**: 處於 **唯讀狀態**。禁止直接呼叫 `file_write` 或 `git_commit`。
- **產出**: 結構化任務清單 (Task Manifest)。

### 2. Executor (Inner Loop - 執行環)
- **職責**: 負責並行執行 DAG 任務、物理修正代碼與執行測試。
- **物理約束**: 處於 **原子 Worktree** 中。每次執行必須獨立且可回滾。

## 🛡️ 意圖純度守衛 (Intent Purity Guard)
為了防止 Planner 產生「幻覺」並試圖直接修改文件，調度器內置了純度守衛：
- **Blocklist**: 攔截 Planner 層的所有寫入類工具調用（如 `replace_file_content`）。
- **Violation Trigger**: 一旦偵測到越權行為，立即拋出 `IntentViolation` 並強制中斷當前任務鏈。

## 🧱 服務分層 (Service Stratification)
| Domain | Key Service | Architecture |
| :--- | :--- | :--- |
| **Planning** | `ProjectPlanner` | Outer Loop |
| **Routing** | `CapabilitySelector` | Bayesian Route |
| **Execution** | `DualLoopOrchestrator` | Inner Loop |
| **Repair** | `RLM_Service` | Recursive Loop |

## ⚙️ 核心特徵
- **Atomic Init**: 所有服務由 `bootstrap.py` 原子化產出。
- **Seam Integrity**: 物理保證 L4 指揮官永遠不會越過 `Coordinator` 直接操作 Drone。

## Role / responsibility
- 聚合核心路由、審核與執行步驟，維持 Orchestrator 的行為可預期與可回溯。 [Source: nexus/core/orchestrator.py]
- 將服務註冊、路由決策、回傳訊息統一到單一執行框架。 [Source: nexus/engine/bootstrap.py]

## Upstream
- `nexus/core/orchestrator.py`：定義主循環節點與錯誤恢復。 [Source: nexus/core/orchestrator.py]
- `nexus/core/state_contracts.py`：規範 state 流轉。 [Source: nexus/core/state_contracts.py]

## Downstream
- 被 CLI 與 route smoke 調度呼叫，回傳 `NexusReceipt` 供驗證。 [Source: scripts/engine/nexus_cli.py]
- 影響 `nexus/core/policy_manager.py` 的 policy/event 記錄。 [Source: scripts/ops/ci_gate.py]

## Related modules / files
- `nexus/core/orchestrator.py`: 核心循環實作。 [Source: nexus/core/orchestrator.py]
- `nexus/core/state_contracts.py`: 狀態機與驗證邏輯。 [Source: nexus/core/state_contracts.py]
- `nexus/engine/bootstrap.py`: 初始化與服務組裝。 [Source: nexus/engine/bootstrap.py]

## Source notes
- 本頁以實際路徑回收為主，不以 legacy 文字說明覆蓋實作。 [Source: scripts/engine/nexus_cli.py]

## Open questions / conflicts
- [ ] 是否保留 `campaign_master_loop` 的同名替代流程，還是以新 seam 命名為主。 [Source: nexus/engine/bootstrap.py]

---
**[Source: nexus/core/orchestrator.py]**

[[System Overview]]

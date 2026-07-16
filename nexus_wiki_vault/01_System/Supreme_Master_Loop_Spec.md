---
aliases: '[P-X-D-R-A-C, Master Loop Spec]'
confidence: high
last_compiled: '2026-07-13'
owner: agent
status: production
type: system
tags: '[core, architecture, loop]'
title: Supreme Master Loop Specification
---

# Supreme Master Loop (P-X-D-R-A-C)

## 核心定義
Supreme Master Loop 已進入 **Production** 階段。它將開發與治理統合成一個具備自律性、強檢核性、且 L4/L3 邊界嚴格定義的「大閉環」。

在架構實體上，它由兩層組成：
1. **L4 Campaign Orchestrator (`campaign_master_loop`)**: 負責 DAG 並行排程、多節點分發與全域里程碑（Milestone）管控。
2. **L3 Task Pipeline (`NexusPipeline`)**: 負責執行單一節點（Node）的 **P-X-D-R-A-C 六階段** 閉環，將開發與治理統合成實體檢核。

## 六大階段 (The 6 Phases)

### Phase 1: Plan (P) - 戰略拆解
- 使用 `CampaignGeneral` 將模糊意圖拆解為任務圖 (DAG)。
- 定義 `StrategicEnvelope` 傳遞戰略封套與全域約束。

### Phase 2: eXecute (X) - 實體執行
- 委派 `TacticalDrone` 在物理沙盒中執行代碼修改。
- 監控 `Sense-Think-Act` 循環，確保符合 `DroneProtocol`。

### Phase 3: Document (D) - 同步紀錄
- 強制更新 `Governance Changelog` 與 `Learning Matrix`。
- 實作 Wiki 與 Git 歷史的物理對位。

### Phase 4: Review (R) - 邏輯審查
- 觸發 `Codex Challenge` (對抗性審查) 或跨模型 A/B 邏輯檢驗。

### Phase 5: Audit (A) - 物理審計
- 執行 `acceptance-check` 並讀取 `hallucination_evidence.json`。
- 計算 `Hallucination Index (HI)` 分數，低於門檻者阻斷。

### Phase 6: Closeout (C) - 晉升結案
- 簽署 `Task Contract Seal`。
- 執行 `Atomic Promotion` 將影子補丁正式晉升至主線。

## 技術實作 (Implementation)
- **Commander**: `nexus/core/campaign_general.py` (L4 指揮官層)。
- **Runner**: `nexus/core/cli_runner_async.py` (非同步執行主循環)。
- **Hardening**: 已實作 `1-bit Core (OneBitGate)` 進行節點晉升判定。
- **Interface**: `scripts/engine/nexus_cli.py nexus run`。

## nexus run 完整執行鏈 (2026-07-13 驗證)

```
nexus run <task>
  |
  +-- detect macro task?
  |   |
  |   +- YES: CampaignGeneral -> campaign_master_loop
  |   |       (decompose -> delegate -> collect)
  |   |
  |   +-- NO: execute_single_task_via_service()
  |           |
  |           +-- canonical_task_seam.py
  |               +-- infer_task_kind(task) -> "bug" | "feature"
  |               +-- NexusCommandService.execute_bug/execute_feature()
  |                   |
  |                   +-- NexusEngine.run_bug/run_feature()
  |                   |   |
  |                   |   +-- _run_task_pipeline()
  |                   |       |
  |                   |       +-- IntentIntakeClassifier.classify()
  |                   |       +-- detect direct_mode?
  |                   |       |   +-- YES: bypass P-X-D
  |                   |       |   +-- NO: NexusPipeline.run()
  |                   |       |
  |                   |       +-- NexusPipeline.run()
  |                   |           |
  |                   |           +-- P: Plan (priority 10)
  |                   |           +-- X: Research (priority 20, conditional)
  |                   |           +-- D: Diagnose (priority 25, VETO->replan)
  |                   |           +-- R: Repair (priority 30)
  |                   |           |   |
  |                   |           |   +-- select_self_heal_route()
  |                   |           |   |   +-- try_local_repair() [deterministic]
  |                   |           |   |   +-- _swarm_repair() [proxies to local]
  |                   |           |   |
  |                   |           |   +-- NEXUS_USE_SURGICAL_REPAIR?
  |                   |           |   |   +-- BattlesuitGateway.surgical_ask()
  |                   |           |   |
  |                   |           |   +-- failure? -> _research_failure_intel()
  |                   |           |
  |                   |           +-- A: Audit/Acceptance (priority 40)
  |                   |           +-- C: Crystallize (priority 50)
  |                   |
  |                   +-- _run_completion_gate()
  |                       +-- evaluate_completion()
  |                       +-- write report bundle
  |
  +-- (fallback) _execute_task_workflow()
      +-- forecast_gate -> autonomic_routing
      +-- context_enrichment
      +-- repair_setup -> repair_loop.run() (max 3 attempts)
```

## Repair Phase 路由 (2026-07-13 驗證)

Repair phase 走的是 `select_self_heal_route()`，不是 `LocalModelExecutor`：

```
RepairPhaseHandler.run(state, context)
  |
  +- select_self_heal_route()
  |   |
  |   +-- backend_used == "fail-closed"?
  |   |   +-- YES: try_local_repair() [deterministic, NOT LocalModelExecutor]
  |   |   +-- NO: _swarm_repair() [proxies to try_local_repair]
  |   |
  |   +-- try_local_repair() 行為：
  |       +- guard: benchmark_run must be truthy
  |       +- regex match: "fix missing '<module>' import in <file>"
  |       +- _insert_import() -> write file -> py_compile.verify
  |       +-- tokens_used = 0 (always)
  |
  +-- NEXUS_USE_SURGICAL_REPAIR?
  |   +-- YES: BattlesuitGateway.surgical_ask() + apply_patch_v2()
  |
  +-- failure? -> _research_failure_intel() -> GitHub Issues via UCCRouter
```

**重要澄清**：`try_local_repair()` 是 deterministic benchmark repair，不是 Qwen/Ollama 模型執行。

## 關鍵缺口

1. **Canonical CLI 沒有 Executor Dispatch Bridge**: 一般 `nexus run` 的 Repair phase 走 deterministic `try_local_repair()`，不是 `LocalModelExecutor`
2. **LocalModelExecutor 主要 caller 是 benchmark scripts**: 非日常 CLI
3. **World A (Agent-operated Nexus) 與 World C (Local Armor) 沒有 bridge**

---
**[Source: nexus_wiki_vault/01_System/Supreme_Master_Loop_Spec.md]**

## One-sentence summary
本頁定義 Supreme Master Loop 的 P-X-D-R-A-C 執行骨架，作為系統治理、執行與驗收的一致控制面。

## Role / responsibility
- 固定主循環邊界，將調度、執行、審計與結案流程對齊到可驗證規格。

## Upstream
- [[01_System/MUSE_PROTO|MUSE_PROTO]]
- [[01_System/Errors_Enum|Errors Enum]]

## Downstream
- [[01_System/System Relationship and Dependency Graph|System Relationship and Dependency Graph]]
- [[06_Ops/Ops - CI Failure Playbook|CI Failure Playbook]]

## Related modules / files
- [Source: scripts/engine/nexus_cli.py]
- [Source: nexus/core/campaign_general.py]
- [Source: nexus/engine/phases/repair.py]
- [Source: nexus/engine/phases/local_repair.py]
- [[System Overview]]

## Source notes
- 2026-07-13: 基於 source-level 驗證更新 Repair phase 路由分析。

## Open questions / conflicts
- P 與 X 的邊界是否需要額外加入「工具溝通超時」的硬件性檢核？
- 如何在不改變 World A 控制鏈的前提下，讓 LocalModelExecutor 成為 Canonical CLI 的正式 backend？

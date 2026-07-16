---
aliases:
- v24.7 Architectural Gaps
- Nexus architecture gap analysis
confidence: high
last_compiled: '2026-07-13'
owner: agent
related_pages: '[[06_Ops/Ops - Wisdom Layer v22 Architecture.md]]'
source_of_truth: refactor_pipeline_composition_spec.md
status: active
tags: '[research, architecture, gaps]'
title: ARCHITECTURAL_GAP_ANALYSIS_V24
type: research
version_scope: '[v24.7, v28]'
---

# Nexus Architectural Gap Analysis (2026-07-13 Update)

## One-sentence summary
本頁評估 Nexus 當前架構差距，基於 `codex/local-armor-baseline-integration` 分支 (HEAD `ffae4fe20`) 的 source-level 驗證結果。

## Role / responsibility
- 建立三條執行鏈的缺口盤點與驗證狀態，做為重構順序依據。
- 對每個缺口定義是否可交付、是否可量化驗證。

## Upstream
- 來自架構審查、效能報告與 Runtime 事故觀測。

## Downstream
- `05_Protocols/Protocol - Engineering Discipline.md`
- `wiki/refactor_pipeline_composition_spec.md`
- `06_Ops/Ops - Wisdom Layer v22 Architecture.md`

## Related modules / files
- `nexus/engine/pipeline.py`
- `nexus/engine/coordinator.py`
- `nexus/engine/phases/repair.py`
- `nexus/services/local_heal/local_model_executor.py`

## Source notes
- 依 v28.3 版本回顧資料與近況指標整理。[Source: .nexus/graph/index.md]
- 2026-07-13: 基於 source-level 驗證更新三條執行鏈分析。

## 三條執行鏈概覽

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Nexus 系統全景                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │  世界 A             │  │  世界 B          │  │  世界 C       │  │
│  │  Agent-Operated     │  │  Benchmark       │  │  Local Armor  │  │
│  │  Nexus Governance   │  │  A/B Harness     │  │  Executor     │  │
│  │                     │  │                  │  │               │  │
│  │  入口:              │  │  入口:           │  │  入口:        │  │
│  │  enforced.sh        │  │  capability_ab_  │  │  LocalModel   │  │
│  │  -> gemini CLI      │  │  runner.py       │  │  Executor.run │  │
│  │  -> nexus CLI       │  │  -> LocalModel   │  │               │  │
│  │                     │  │  Executor        │  │  實際 caller: │  │
│  │  用途:              │  │                  │  │  benchmark    │  │
│  │  日常開發治理        │  │  用途:           │  │  scripts only │  │
│  │                     │  │  證明 uplift     │  │               │  │
│  │  已驗證:            │  │                  │  │  已驗證:      │  │
│  │  governance wearing │  │  已驗證:         │  │  full local   │  │
│  │                     │  │  Bare vs Nexus   │  │  pipeline     │  │
│  │  未驗證:            │  │  比較            │  │               │  │
│  │  runtime local      │  │                  │  │  未驗證:      │  │
│  │  assist injection   │  │  未驗證:         │  │  日常 CLI     │  │
│  │                     │  │  作為產品 runtime │  │  dispatch     │  │
│  └─────────────────────┘  └──────────────────┘  └───────────────┘  │
│                                                                     │
│  ──────────────────── 最大缺口 ──────────────────                    │
│  world A <-> world C 之間沒有 runtime bridge                       │
│  world B 是驗證儀器，不是產品主線                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 核心缺口分析 (7 Gaps)

### Gap 1：Canonical CLI 沒有 Executor Dispatch Bridge

```
CapabilityPlanner 可以選中 local_model_executor
                |
                v
signal_snapshot 包含 execution_topology
                |
                v
          ??? 缺少這段 ???
                |
                v
LocalModelExecutor.run()
```

目前只有 benchmark runner（capability_ab_runner.py）具備這段橋接。一般 `nexus run` 的 Repair phase 走的是 deterministic `try_local_repair()`，不是 `LocalModelExecutor`。

### Gap 2：Online Agent Path 與 Local Armor Path 完全分離

```
世界 A (Online Agent)           世界 C (Local Armor)
  |                               |
  +- briefing                     +- LocalModelExecutor
  +- rules                        +- Qwen/Ollama
  +- CLI commands                 +- candidate/verifier
  +- governance                   +- receipt/ledger
  |                               |
  +-- 沒有自動 Local Assist   <-- 無 bridge
```

Online Agent 收到的是治理規則，不是 local diagnosis、local candidate 或 local verifier feedback。

### Gap 3：cloud_with_local_assist 使用 Fake Cloud

```
Planner: "我要 cloud_with_local_assist"
  |
  v
LocalModelExecutor: topology = "cloud_with_local_assist"
  |
  +- Stage 1: local diagnosis (deterministic, OK)
  +- Stage 2: FakeCloudCandidateProvider (EMPTY!)
  +- Stage 3: cheap verifier (deterministic, OK)
  +-- fall through to single_local_model
```

Contract 已存在，但沒有接到真實 Gemini/Codex/Grok CLI。

### Gap 4：Local Assist 沒有 Agent-facing 輸出契約

即使未來一般 CLI 呼叫了 LocalModelExecutor，目前也缺少一個清楚的 agent-facing envelope：

```
缺少的 envelope 欄位：
  +- local_diagnosis
  +- recommended_files
  +- semantic_assertions
  +- candidate_options
  +- verifier_feedback
  +- local_confidence
  +- cloud_call_recommendation
  +-- receipt_path
```

### Gap 5：兩個控制模式沒有共同的任務 lineage

```
世界 A: Agent-operated Nexus
  +- task_id (Gemini session)
  +- workspace revision (agent controlled)
  +-- receipt重點: governance evidence

世界 C: Nexus-operated LocalModelExecutor
  +- task_id (benchmark fixture)
  +- workspace revision (isolated tempdir)
  +-- receipt重點: candidate/verifier evidence
```

尚未證明它們共用 task_id、workspace revision、CapabilityPlan、evidence hash、candidate lineage。

### Gap 6：benchmark_run 語義混亂

`benchmark_run` 目前同時被當成：

1. CLI 兼容預設（NexusCommandService 預設 True）
2. Deterministic local repair gate（try_local_repair 依賴此旗標）
3. Benchmark execution signal

語義混用可能造成錯誤路由或假 local repair 證據。

### Gap 7：Local Assist 節省 token/時間目前沒有入口可量測

日常 Online Agent 路徑沒有自動進入 LocalModelExecutor，因此無法可靠量測：

- 本地診斷減少多少 Online prompt
- 本地先解避免多少 Online call
- 本地 retry 避免多少 Online retry
- 本地 review 是否縮短 Agent 迴圈

## 系統狀態總結

```
目前最準確的系統狀態：

  Online Agent Wearing       = governance/tool layer proven
  Canonical Nexus CLI        = pipeline exists
  Local Model Armor          = benchmark runtime proven
  Online + Local Hybrid      = NOT WIRED
  Universal execution seam   = MISSING
```

## Open questions / conflicts
- [ ] L4 任務規劃者（Project Planner）是否需在本輪先行接軌。
- [ ] 是否要優先推進 self-assembly skill 相關能力，或先補上 clarifying loop。
- [ ] 如何在不改變 World A 控制鏈的前提下，讓 LocalModelExecutor 成為 Canonical CLI 的正式 backend？
- [ ] cloud_with_local_assist 的 FakeCloudCandidateProvider 何時替換為真實 Cloud provider？

---
[[System Overview]]

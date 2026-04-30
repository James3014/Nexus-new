---
aliases:
- Capability Routing
- Smart Routing
- Routing Engine
- Central Nervous System
confidence: high
last_compiled: 2026-04-30
owner: agent
related_pages:
- '[[Module - Core Orchestrator]]'
- '[[Protocol - RLM Recursive Learning]]'
- '[[Protocol - Evidence Chain]]'
source_of_truth: docs/arch/NEXUS_ROUTING_LONG_PLAN_V2.md
status: active
tags:
- protocol
- routing
- capability
- argmax
- msa
title: Protocol - Capability Routing
type: protocol
version_scope:
- v24.7
- v26
---

# Protocol - Capability Routing (The Central Nervous System)

## 🧬 核心架構圖 (System Architecture)

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Nexus Task Intake                               │
│                 user task / benchmark task / CI event / recovery event        │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         S Phase: Spec / Scope Binding                         │
│  - task type, risk, files, expected evidence, budget, user intent             │
│  - hard constraints: forbidden paths, max files, model/provider eligibility   │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Five Pillars Context Plane                             │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│ LanceDB              │ Memory               │ MemPalace                     │
│ tactical retrieval   │ long-term lessons    │ policy / boundary / audit     │
├──────────────────────┼──────────────────────┼───────────────────────────────┤
│ Belief               │ Artifact             │ Claim                         │
│ confidence / doubt   │ evidence bundle      │ verified / partial / unknown  │
└───────────┬──────────┴───────────┬──────────┴───────────────┬───────────────┘
            │                      │                          │
            ▼                      ▼                          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    P Phase: Capability Route Planner                          │
│                                                                              │
│  Capability state model:                                                      │
│  required | optional | conditional | forbidden                                │
│                                                                              │
│  Objective:                                                                   │
│  argmax(expected_value - cost - risk_penalty) subject to governance gates      │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     Capability Composition Engine                             │
├─────────────────────┬─────────────────────┬─────────────────────────────────┤
│ CodeIntel           │ Research            │ Hyper                           │
│ impact/context      │ citation/RAG        │ heavier search/repair route     │
├─────────────────────┼─────────────────────┼─────────────────────────────────┤
│ Nightshift          │ Swarm               │ Drone                           │
│ recovery/escalation │ multi-review        │ delegated artifacts             │
├─────────────────────┼─────────────────────┼─────────────────────────────────┤
│ Ultra Review        │ Autoreason          │ DDTree                          │
│ sandbox hard gate   │ candidate judging   │ branch pruning / acceleration   │
└─────────────────────┴─────────────────────┴─────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         X / D / R Dynamic Replan Loop                         │
│                                                                              │
│  X: gather evidence / code context / research                                 │
│  D: decision gate, MemPalace, Belief confidence, risk policy                  │
│  R: repair / solve / candidate generation                                     │
│                                                                              │
│  Replan triggers:                                                             │
│  - evidence missing      -> add Research / CodeIntel                          │
│  - high-risk change      -> add Ultra Review / Swarm                          │
│  - repeated A rejection  -> add Autoreason / Hyper / Nightshift               │
│  - too slow / too costly -> prune via DDTree or downgrade optional abilities  │
│  - low confidence        -> tighten gates, require more artifacts             │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         A Phase: Acceptance / Evidence                         │
│                                                                              │
│  - tests, hidden verifier, code impact evidence, artifact bundle              │
│  - capability receipt: what was used, why, cost, result                       │
│  - fail-closed if required evidence is missing                                │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         C Phase: Closure / Learning                            │
│                                                                              │
│  - write lessons to Memory / Findings                                         │
│  - update route oracle / benchmark evidence                                   │
│  - mark stale rules for lifecycle review                                      │
│  - feed JIT / benchmark / route planner history                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

## ⚖️ 路由優化目標 (Optimization Objective)
新路由不再基於簡單的關鍵字匹配，而是執行貝葉斯決策優化：

$$ \text{Target} = \text{argmax}(\text{Expected Value} - \text{Cost} - \text{Risk Penalty}) $$

- **Expected Value**: 基於 `Memory` 與 `LanceDB` 歷史相似案例的修復機率。
- **Cost**: Token 消耗與 Wall-clock 時間成本。
- **Risk Penalty**: 基於 `CodeIntel` 與 `JIT` 偵測到的代碼敏感度、影響範圍。
- **Subject to**: `MemPalace` 與 `CapabilityGate` 的硬性治理約束。

## 🔄 X / D / R 動態重新規劃 (Dynamic Replan)
系統在執行過程中具備「自我意識」，會根據 `Belief` 信號實施動態重排：
- **證據缺失**：自動補掛 `Research`。
- **高風險**：強制升級至 `Ultra Review` 與 `Swarm`。
- **連續失敗**：觸發 `NightShift` 長程恢復。

## 🏗️ 能力組合引擎 (Capability Composition)
- **CodeIntel**: 代碼影響圖譜感知。
- **Autoreason**: 候選方案評審與多維 Borda 投票。
- **DDTree**: 推理樹剪枝與解碼加速。
- **Ultra Review**: 沙盒硬隔離驗證門。

---
[Module - Core Orchestrator](../02_Modules/Module - Core Orchestrator.md)

---
aliases:
- Capability Matrix
- Nexus Capability Inventory
- 18 Rings
- 9 Rings
confidence: high
last_compiled: 2026-04-30
owner: agent
related_pages:
- '[[Protocol - Capability Routing]]'
- '[[Module - Core Orchestrator]]'
- '[[Protocol - Evidence Chain]]'
source_of_truth: docs/arch/NEXUS_ROUTING_LONG_PLAN_V2.md
status: active
tags:
- module
- capability
- inventory
- matrix
- routing
title: Module - Capability Matrix
type: module
version_scope:
- v26
---

# Module - Capability Matrix (v26 Hardened)

## 🧬 靈魂五位一體 + MSA, JIT, RLM
Nexus 的能力建立在「五支柱」與「三機制」的基石之上。

| 支柱 / 機制 | 負責維度 | 在管線中的作用 |
| :--- | :--- | :--- |
| **LanceDB** | 戰術數據 | 提供相似案例檢索與 JIT RAG 上下文。 |
| **Memory** | 長期經驗 | 存儲 FindingsCard，驅動跨任務學習。 |
| **MemPalace** | 倫理邊界 | 執行工具封鎖、黑名單過濾與經驗永久化。 |
| **Belief** | 主觀認知 | 維護信心狀態，控制路由的升級與降級。 |
| **Artifact** | 客觀證據 | 產出實體工件，作為 Claim 斷言的物理基礎。 |
| **Claim (斷言)** | 驗證維度 | 決定能否公開宣稱任務完成，杜絕敘事幻覺。 |
| **MSA** | 記憶稀疏注意 | 解耦記憶容量與推理能力，實現海量代碼庫感知。 |
| **JIT** | 及時風險預測 | 在執行前偵測代碼敏感度與影響範圍。 |
| **RLM** | 遞迴學習機 | 驅動有預算約束的「自癒 - 驗證」循環。 |

---

## 🏆 Nexus 18 項核心能力盤點

### 1. 偵查與上下文 (Recon & Context)
*   **CodeIntel**: `code scan / impact / context`。用於程式碼圖譜、影響分析、上下文注入。
*   **Research / Learn**: `research:auto-flow`, `learn:ingest`。用於 RAG、學習閉環、研究型路由。
*   **Memory / LanceDB**: `findings_memory`。長期經驗、語義去重、發現檢索。

### 2. 推理與修復 (Reasoning & Repair)
*   **Hyper / Sprint**: `sprint_service`。用於多候選修復、快速局部自癒。
*   **Nightshift**: `nightshift_runner_service`。用於 Hyper 失敗後的長程恢復、貝葉斯溫啟動修復。
*   **Autoreason**: `autoreason_service`。用於候選方案評審、信心/語義判定（Borda 投票）。
*   **DDTree**: 推理加速層。執行推理樹剪枝與解碼加速。

### 3. 協作與多代理 (Collaboration & Multi-Agent)
*   **Swarm**: `nexus swarm`。包含 Task 建立、File Lock、並行提交與 Fleet 指標。
*   **Drone**: `drone-hud`。委派 Worker、戰術執行與即時狀態監控。
*   **Multi-Agent**: 協調不同專長的 Agent 進行共識決策。

### 4. 治理與風險控制 (Governance & Risk)
*   **MemPalace / Policy**: `mem_palace`, `policy_gate`。倫理/規則/Phase-based 門禁。
*   **Ultra Review**: `nexus ultra-review`。沙盒硬隔離、Ghost Regression 偵測。
*   **Belief Engine**: 信心驅動路由的決策訊號源。
*   **Forecast / Pregate**: `forecast_gate_service`。執行前風險預判與計畫品質審查。

### 5. 驗收與進化 (Acceptance & Evolution)
*   **Artifact / Claim**: `delivery-gate`, `claim_service`。可驗證交付與斷言狀態管理。
*   **Sandbox / Replay**: `nexus sandbox`, `replay_runner`。隔離執行與可回放驗證。
*   **Benchmark / Meta-Opt**: `research:meta-opt`。自我評測、ROI 分析、能力自動調參。
*   **Autonomic Routing**: `autonomic_router`。智慧路由中樞，統籌能力組合。

### 6. 周邊與產品化 (Peripheral & Product)
*   **UI Validator**: `scripts/ui-validator.py`。基於 Playwright 的 Agentic UI 探索驗證。
*   **Stress Test**: `scripts/engine/commands/stress_test.py`。反遞迴、背壓感知與高壓壓力測試。

---

## 📊 能力空間分類 (9 類)

1.  **主執行**: Direct Loop, Rewrite, Repair Loop, Hyper, Nightshift。
2.  **偵查與上下文**: CodeIntel, Research Route, XRay, Learn, LanceDB。
3.  **記憶與學習**: Memory, Findings, Learn Scheduler, Learning Closure。
4.  **推理與加速**: Autoreason, DDTree, Belief, Forecast Gate。
5.  **協作與多代理**: Swarm, Drone, File Lock, Integration Manager。
6.  **治理與風險控制**: MemPalace, Policy Gate, Capability Gate, Ultra Review。
7.  **驗收與交付**: Artifact Gate, Claim Gate, Delivery Gate, Replay/Sandbox。
8.  **自我進化**: Benchmark, Meta-Opt, Capability Autotune, Regression Guard。
9.  **產品化能力**: Registry, Metabolism, Oracle, UI Validator, Stress Test。

---

## 🚀 路由優先級 (Strategic Registry Priority)

*   **核心必進 (P0)**: CodeIntel, Research, Hyper, Nightshift, Swarm, Drone, Ultra Review, Autoreason, DDTree。
*   **五位一體必進 (P0)**: LanceDB, Memory, MemPalace, Belief, Artifact, Claim。
*   **交付必進 (P1)**: Pregate, Plan Quality, Sandbox, Delivery Gate, Acceptance Check。
*   **自我進化必進 (P1)**: Benchmark, Meta-Opt, Learning Closure, Regression Guard。
*   **第二波 (P2)**: Direct Mode, Multi-Agent, File Lock, Metabolism, Oracle, UI Validator, Stress Test。

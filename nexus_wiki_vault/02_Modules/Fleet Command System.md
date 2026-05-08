---
aliases:
  - Fleet Command
  - Swarm Orchestration
  - Federated Learning
confidence: high
last_compiled: 2026-05-06
owner: agent
related_pages:
  - "[[Module - Router Decision Flow]]"
  - "[[00_Home/System Overview]]"
  - "[[06_Ops/Ops - CI/CD Promotion Gate]]"
source_of_truth: scripts/ops/federated_engine_v09.py
status: active
tags:
  - module
  - fleet
  - orchestration
title: Fleet Command System
type: module
version_scope:
  - v23
  - v26
---

# Module: Fleet Command System (v23.7)

## One-sentence summary
艦隊指揮系統負責任務分解、跨節點派工與回收關鍵產出，支持多任務並行與可追溯交付。 [Source: scripts/ops/federated_engine_v09.py]

## Role / responsibility
- 定義 Swarm 內部的任務調度與階段化回報機制。 [Source: scripts/engine/nexus_cli.py]
- 將多來源訊號整理成可驗證執行計畫，避免任務失焦。 [Source: scripts/ops/capability_route_smoke.py]
- 提供可復原的作業入口與續跑條件。 [Source: scripts/ops/ci_gate.py]

## Upstream
- `System Overview` 提供整體系統邏輯邊界。 [Source: 00_Home/System Overview.md]
- `Router Decision Flow` 提供任務分類與路由策略配合。 [Source: 02_Modules/Router_Decision_Flow.md]

## Downstream
- 交付結果回寫給 CI Promotion Gate、路由與能力門控。 [Source: scripts/ops/ci_gate.py]
- Swarm 執行結果可被 `Ops - Weekly Governance Report` 匯總。 [Source: 06_Ops/Ops - Weekly Governance Report.md]

## Related modules / files
- `scripts/ops/federated_engine_v09.py`: 入口與編排參數管理。 [Source: scripts/ops/federated_engine_v09.py]
- `scripts/engine/nexus_cli.py`: 任務 CLI 進入點。 [Source: scripts/engine/nexus_cli.py]
- `nexus/core/orchestrator.py`: runtime 主循環與風控邏輯。 [Source: nexus/core/orchestrator.py]

## Source notes
- 本頁基於實際可執行腳本與 CI 入口進行整理。 [Source: scripts/ops/federated_engine_v09.py]
- 會依項目設定決定是否啟用聯邦聚合。 [Source: scripts/engine/nexus_cli.py]

## Open questions / conflicts
- [ ] 聯邦學習參數是否仍適用於新版本租戶模型。 [Source: scripts/ops/federated_engine_v09.py]
- [ ] Swarm 任務是否需要加入 MSA 雙模檢索回饋。 [Source: 02_Modules/Router_Decision_Flow.md]

## 📌 概述
艦隊指揮系統是 Nexus 從「單體演化」轉向「分散式多工協作」的核心。它透過主管引擎 (Supervisor Engine) 實現任務的自動化拆解、委派與總合。

## 🔩 核心組件
1. **Supervisor Engine**: 負責任務的語義拆解 (Decomposition)。
2. **Sensory Probe (Style Ingester)**: 負責吞沒外部環境審美，即時同步 `DESIGN.md`。
3. **Session Metabolism Engine (AutoDream)**: 將任務信號壓縮為 `session_seed.json`，建立任務續接斷點並抑制幻覺續鏈效應。

## 🛠️ 操作指令
- `nexus delegate <task>`: 發動全艦隊合力開發。
- `nexus resume`: 從最後一個物理斷點恢復執行。
- `nexus style-ingest <url>`: 同步外部設計規格。

## 🧬 Federated Learning v0.9 (艦隊演化)

Nexus v0.9 將單機 NAS 優化提升至 **聯邦學習 (Federated Learning)** 級別，實現跨租戶的智慧聚合與隱私保護。

### 核心機制：FedAvg + DP-SGD
- **聚合演算法**: `FedAvg` (Federated Averaging)，透過 `np.mean` 彙整各租戶的 16 維 `router_bias_delta`。
- **隱私防禦**: `DP-SGD` (Differential Privacy)，注入 **拉普拉斯噪聲 (Laplace Noise)**。
    - **隱私預算 (ε)**: 1.0
    - **靈敏度縮放**: 0.002
- **目標 Fitness**: **0.995** (SOTA 級別收斂)。

### 物理實作
- **入口腳本**: `uv run scripts/ops/federated_engine_v09.py`
- **數據載體**: `tenants/tenant-000~009/dna_delta.json`
- **全域 DNA**: `configs/federated_dna.yaml`

## 📈 治理要求
- 所有的 Swarm 工作必須產出物理證據 (`swarm_work.json`)。
- 所有的總合產物必須產出最終清單 (`mission_complete.json`)。
- **聯邦同步**: 必須維持 10/10 的租戶聚合比例，否則 CI 守門拒絕發版。

---
**[Source: scripts/ops/federated_engine_v09.py]**

[[System Overview]]

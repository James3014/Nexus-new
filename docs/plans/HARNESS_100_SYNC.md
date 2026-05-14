# 📚 Nexus 學習同步：生產級 Agent Harness (Harness-100)

> **致優化 Agent：**
> 本文件提煉自 `revfactory/harness-100`，並**嚴格映射至 Nexus 當前的 `swarm`、`multi_agent` 以及 `governance / validation gates` 架構**。請以此作為處理多 Agent 協作與路由硬化的決策依據。

---

## 🏗️ I. Harness 核心架構層 (Architecture & Orchestration)

### 1. 三層技能系統 (Three-Layer System)
*   **文獻重點**：明確劃分 Orchestrator (編排層)、Agent-Extending (領域擴展層) 與 External (外部層)。
*   **Nexus 對位實踐**：
    *   **Orchestrator**：對應 Nexus 的 `capability_planner.py` 與 `msa_router`，負責依據 Risk Score 切換 Routing Tier (如 `L1_green_lane` vs `L3_swarm_deep`)。
    *   **Agent-Extending**：對應 Nexus 的 `bdd_acceptance_skill`、`architecture_scout`，提供專業領域約束。
    *   **External**：對應 Nexus 的 `sandbox`、`external_doc_scout`。
    *   **行動指引**：Agent 在選擇 Capability 時，應遵循此三層分離原則，避免將「外部調用」與「邏輯編排」混雜在同一節點，導致 `blast_radius` (影響半徑) 失控。

### 2. 專家團隊協作模式 (Agent Team Mode)
*   **文獻重點**：4-5 位領域專家 + 1 位 QA/Reviewer 的協作網路。
*   **Nexus 對位實踐**：
    *   對應 Nexus 的 `swarm`、`drone` 與 `judge_panel` / `ultra_review`。
    *   **行動指引**：在觸發 `L3_swarm_deep` 時，Nexus 應利用 `judge_panel` 作為最終的 QA Reviewer。證據輸出 (`evidence_outputs`) 必須包含 `panel_votes` 與 `consensus`，不得由單一 Drone 節點強行跨過 `claim_gate`。

---

## 🛡️ II. 治理與控制層 (Governance & Control)

### 3. 領域框架的物理約束 (Embedded Frameworks)
*   **文獻重點**：將真實世界標準 (如 SOLID, OWASP) 作為 Agent 的底層物理定律。
*   **Nexus 對位實踐**：
    *   對應 Nexus 的 `mempalace_gate`、`asi_constraint_extractor` 與 `belief` Mechanics。
    *   **行動指引**：在 `P` (Plan) 與 `D` (Design) 階段，必須強制經過 `asi_constraint_extractor` 抓取 `blocked_assumptions`。若 Agent 產生的計畫違反領域框架，`pregate` 必須直接 `FAIL`，這與 harness-100 將框架「寫死」的理念一致。

### 4. 任務編排與有向無環圖 (DAG Dependencies)
*   **文獻重點**：嚴格的任務排序與並行管理。
*   **Nexus 對位實踐**：
    *   對應 Nexus Capability Node 中的 `dependencies` 與 `parallelizable_with` 設計。
    *   **行動指引**：在執行如 `codeintel` 與 `research` 時，必須利用 `parallelizable_with` 實現真正的非阻塞並行 (Non-blocking execution) 以降低 Wall Time，這正是 Nexus 解決 `cost_efficiency` 下降的關鍵。

---

## ⚙️ III. 穩健性與防護層 (Robustness & Fallbacks)

### 5. 觸發邊界與容錯 (Boundaries & Fallbacks)
*   **文獻重點**：定義明確的 Retry、Skip 與 Fallback 條件。
*   **Nexus 對位實踐**：
    *   對應 Nexus 的 `repair_loop`、`hyper` 與 `semantic_failure_sensor`。
    *   **行動指引**：當 `artifact_gate` 拒絕交付時，`semantic_failure_sensor` 必須輸出精確的 `retry_policy` (重試策略)。不能無限制盲目重試，應依賴 `budget_safety_floor_preserved` 來觸發強制 Fallback (如退回 `human_review` 或降級 Lite mode)。

### 6. 結構化輸出與交叉驗證 (Validation & Cross-Check)
*   **文獻重點**：透過特定模板與獨立的 Reviewer Agent 收斂發散的 LLM 輸出。
*   **Nexus 對位實踐**：
    *   對應 Nexus 的 `artifact_gate`、`delivery_gate` 與 `claim_gate`。
    *   **行動指引**：所有 `drone` 與 `swarm` 的產出，必須經過獨立的 `delivery_gate` (確保沒有 Trust Mismatch) 與 `claim_gate` (確保商業邏輯通過 BDD) 的雙重交叉驗證，方可形成 `evidence_bundle` 進行結算。

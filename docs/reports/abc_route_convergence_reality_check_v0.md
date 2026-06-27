# MG / Nexus / ABC Integration Reality Check — No Runtime Change (v0)

本報告針對 A (Main Engine)、B (Local Heal)、C (Hybrid Route Schema) 三個部分在目前 codebase 的實體檔案位置與 symbol 進行盤點與現狀對比，做為未來整合時的架構依據。

---

## A 定義盤點：Main Engine

Main Engine 組件主要負責全域 Capability 的規劃、決策與靜態/動態約束。

### 1. CapabilityPlanner
- **檔案路徑**：[capability_planner.py](file:///Users/jameschen/Workspace/nexus/nexus/engine/capability_planner.py)
- **核心 Symbol**：`CapabilityPlanner`
- **現狀對比**：
  - `CapabilityPlanner.plan(...)` 負責執行全域能力拼裝，讀取 `CapabilityNode` 配置並根據 `CapabilitySignalSet` 輸出 `CapabilityPlan`。
  - 目前其 `plan` 邏輯包含 `_apply_route_cost_policy`、`_apply_s2t_policy_promotion` 等細粒度治理規則，但此處並未直接感知 `local_heal` 服務的內部狀態。

### 2. CapabilityPlan
- **檔案路徑**：[capability_contracts.py](file:///Users/jameschen/Workspace/nexus/nexus/engine/capability_contracts.py)
- **核心 Symbol**：`CapabilityPlan`
- **現狀對比**：
  - 為 `dataclass(frozen=True)`，記錄選中（selected）、必需（required）、可選（optional）、待定（pending）、禁止（forbidden）的能力列表及 replan_trace。

### 3. RouteDecision
- **檔案路徑**：[capability_contracts.py](file:///Users/jameschen/Workspace/nexus/nexus/engine/capability_contracts.py)
- **核心 Symbol**：`RouteDecision`
- **現狀對比**：
  - 為 `dataclass(frozen=True)`，包含了全域路由的最終產出欄位。
  - 目前具有 `executor_controls`、`receipt_requirements`、`public_claim_scope` 與 `routing_tier` 等配置。

### 4. executor_controls
- **檔案路徑**：[capability_contracts.py](file:///Users/jameschen/Workspace/nexus/nexus/engine/capability_contracts.py)
- **核心 Symbol**：`RouteDecision.executor_controls: dict[str, Any]` / `CapabilityExecutionPlan.executor_controls: dict[str, Any]`
- **現狀對比**：
  - 扮演將 Planner 決策結果向下傳遞至執行期的控制面參數。目前主要是單純的 JSON Dict 結構。

---

## B 定義盤點：Local Heal

Local Heal 組件主要負責本地自我修復循環（Red-Green-Refactor）與本地模型評估。

### 1. HealOrchestrator
- **檔案路徑**：[orchestrator.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/orchestrator.py)
- **核心 Symbol**：`HealOrchestrator`
- **現狀對比**：
  - 核心修復工作流：線性啟動（Reproduction, Planning, Localization） -> 迭代修復迴圈（PatchSynthesis, Verification） -> 審計結算。
  - 執行結束後呼叫 `governance_gate.audit(ctx)` 與 `receipt_writer` 輸出修復憑證。

### 2. pipeline (HealPipeline)
- **檔案路徑**：[pipeline.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/pipeline.py)
- **核心 Symbol**：`HealPipeline`
- **現狀對比**：
  - 作為外部調用 `local_heal` 服務的進入點，將 Legacy `HealContext` 轉換為 V2 `HealContext`，配置各個執行 Phase 後送入 `HealOrchestrator` 或 `CommitteeOrchestrator` 執行。

### 3. local_model_adapter_contract
- **檔案路徑**：[local_model_adapter_contract.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/local_model_adapter_contract.py)
- **核心 Symbol**：`LocalModelAdapterRequest`, `LocalModelAdapterResponse`, `LocalModelAdapterReceipt`, `LocalModelResourcePolicy`
- **現狀對比**：
  - 作為未來本地模型求解路徑的 inert 樁（Stub），禁止任何網絡、模型載入與運行時導入。
  - 內含 `route_truth_source: str = "CapabilityPlanner"`、`public_claim_allowed: bool = False`、`production_ready: bool = False` 等空實作與欄位。

### 4. verifier & receipt
- **檔案路徑**：
  - [evaluation_gate.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/evaluation_gate.py) (`EvaluationGate`)
  - [receipt.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/receipt.py) (`write_repair_receipt`)
- **現狀對比**：
  - `verifier` 對應的是運行時對 Patch 進行 pytest 或執行驗證的閘道器，並非靜態 contract。
  - `receipt` 為修復流程結束後落盤的 JSON 憑證，其包含了運行時實測數據。

---

## C 定義盤點：Hybrid Route Schema 與控制欄位

C 區塊為 A 區與 B 區收斂後的混合路由合約，需要具體定義路由模式與發布權限。

### 1. 概念與需求
- 為了不直接整合 runtime 並建立安全防護，必須從 `CapabilityPlanner` 或本地 `HealOrchestrator` 的控制點抽象出混合路由契約。
- 該契約應確保預設不開啟 local-first、預設不可發布 public claim、預設不將本地 adapter 產出視為真值，並以 `CapabilityPlanner` 做為真值決策的權威來源（route_truth_source）。

### 2. 新增之獨立 Contract：[hybrid_route.py](file:///Users/jameschen/Workspace/nexus/nexus/contracts/hybrid_route.py)
為實踐 C 的規格，在不改動任何 A 與 B 運行時邏輯的前題下，新增此合約檔案，包含：
- **`RouteMode`**: 路由模式列舉 (`local_first`, `public_fallback`, `hybrid`)。
- **`HybridRouteDecision`**: 封裝路由安全欄位之數據類別：
  - `route_mode` (預設 `hybrid`)
  - `public_claim_allowed` (預設 `False`)
  - `production_ready` (預設 `False`)
  - `adapter_output_is_route_truth` (預設 `False`)
  - `route_truth_source` (預設 `"CapabilityPlanner"`)
  - `local_guard` (預設空 Dict)
  - `behavior_changed` (預設 `False`)
- **安全校驗**: 於初始化時強制約束 `route_truth_source` 必須是 `"CapabilityPlanner"`，否則拋出 `ValueError` 以落實 Fail-Closed 機制。

# Agent B: P3 Signal → Execution Topology Data Flow Audit

## 任務
P3 唯讀 audit：追蹤 `signal_snapshot` / `execution_topology` / `route_context` 從 router → CapabilityPlanner → capability_adapter → orchestrator → LocalModelExecutor 的資料流，以及 topology 如何回流到 receipt。

## 限制（違反者退件）
- 🛑 不修改任何 `.py` 檔
- 🛑 不改 `router.py`
- 🛑 不改 `capability_planner.py`
- 🛑 不新增 route / enum / adapter
- 🛑 不接 cloud endpoint
- 🛑 不做 quota tracker
- 🛑 不做 diversity committee
- 🛑 不宣稱 cloud_with_local_assist ready

## 必查檔案（唯讀）
- `nexus/engine/capability_planner.py`
- `nexus/services/local_heal/capability_adapter.py`
- `nexus/services/local_heal/local_model_executor.py`
- `nexus/services/local_heal/local_model_capability_context.py`
- `nexus/services/local_heal/local_committee_candidate_provider.py`
- `nexus/services/local_heal/claim_delivery_gate.py`
- `nexus/services/local_heal/candidate_isolation_gate.py`
- `nexus/contracts/hybrid_route.py`
- `tests/unit/local_heal/test_capability_adapter.py`
- `tests/unit/local_heal/test_local_model_executor.py`
- `tests/benchmark/test_local_model_executor_planner_path.py`

## 產出
`docs/reports/p3_signal_execution_topology_dataflow.md`

### 必須包含章節

#### 1. signal_snapshot schema registry
每個欄位的：型別、預設值、設定層級（router / planner / adapter / executor）、是否為 optional

#### 2. producer → consumer mapping table
格式：

| 欄位 | Producer 模組 | Consumer 模組 | 有無斷點 | 風險 |
|------|---------------|---------------|----------|------|

#### 3. execution_topology 回流路徑
topology 從 executor 產生後，經過哪些模組回到 final receipt

#### 4. route_context 關鍵路徑傳遞檢查
- CapabilityPlanner → adapter → executor 是否完整傳遞
- committee path vs pipeline path 差異

#### 5. P2 修復後殘留斷點歸因
- 檢查 signal_snapshot 是否有欄位未正確往下傳
- 特別注意：`candidate_enabled`、`model_call_allowed`、`isolated_solve_enabled`、`mutation_allowed`、`verifier_allowed`

#### 6. rank_bm25 dependency 判斷
- 是否應改成 optional import + fallback？
- 是否應 mock 在 test 層？
- 建議方案

#### 7. P3 實作前 unblock checklist
基於 audit 發現，列出 P3 implementation 前必須修復的項目

## 驗收標準
1. 報告必須 grounded in actual source code（每個 claim 要有檔案:行號）
2. 不允許模糊描述—每個斷點必須說明影響與風險等級
3. 必須包含 schema registry 和 mapping table（不允許只有散文）

# Routing Refactor P1-P6 Report (2026-05-04)

## 範圍
本輪採「Clean Code / Linus」原則，避免補丁式堆疊：
- 切小
- 模組化
- 解耦
- 關注點分離

## 變更（P1-P2）
目標檔案：
- `nexus/engine/capability_planner.py`

已完成的低風險純函式切分（無行為變更）：
1. `_decide_routing_tier(signals) -> (tier, reason)`
2. `_apply_budget_downgrade(states, reasons, scoring, max_cost) -> (...)`
3. `_build_signal_snapshot(signals, routing_tier, routing_tier_reason) -> dict`

主流程 `plan()` 已改為委派上述函式，降低單函式認知負擔與耦合。

## 測試與驗證（P3-P5）
### Engine 整合集合
- `tests/engine/test_capability_planner.py`
- `tests/engine/test_capability_router.py`
- `tests/engine/test_capability_routing_contracts.py`
- `tests/engine/test_autonomic_routing_service.py`
- `tests/engine/test_route_contracts.py`

結果：`53 passed`

### Ops / Gate / Benchmark 合同集合
- `tests/ops/test_build_test_impact_index.py`
- `tests/ops/test_select_tests.py`
- `tests/ops/test_ci_gate_report_trust_audit.py`
- `tests/ops/test_capability_route_smoke.py`
- `tests/ops/test_nexus_benchmark_preflight.py`
- `tests/ops/test_codex_nexus_ab_smoke.py`

結果：`38 passed`

### 路由基準
- `scripts/ops/router_policy_benchmark.py`

結果：
- precision=1.0
- recall=1.0
- f1=1.0

### Flash smoke（重構後）
- 路徑：
  - `.nexus/reports/flash_speed_smoke_after_refactor/`
- 結果：
  - with_nexus: solve/semantic/trust = `1.0 / 1.0 / 0.0`, avg wall = `36.66s`
  - without_nexus: solve/semantic/trust = `1.0 / 1.0 / 0.0`, avg wall = `24.40s`
  - with_nexus token(all)=`15070`, without_nexus token=`22758.33`

## 判定（P6）
1. 本輪重構屬「可上主幹的安全重構」：整合測試全綠、benchmark 不退化。  
2. 速度面仍未超越 bare，但成本（token）優勢持續存在。  
3. 新路由從「單點補丁」往「可拆可驗證」結構前進，下一輪可進一步拆 `capability_planner` 其餘責任塊。

## P2 重構後補充驗證（同口徑 Flash smoke）
- 路徑：
  - `.nexus/reports/flash_speed_smoke_after_refactor_p2/`
- 摘要：
  - with_nexus（eligible=3）：solve/semantic/trust=`1.0/1.0/0.0`，avg wall=`66.08s`
  - without_nexus（eligible=2, infra_invalid=1 timeout_before_model_call）：solve/semantic/trust=`1.0/1.0/0.0`，avg wall=`40.79s`

說明：
- 本輪出現明顯時間波動（主要在模型/網路側），不宜用單次 smoke 做最終公開宣稱。  
- 工程上判定仍成立：重構未破壞功能正確性（整合測試與 benchmark 全綠）；效能需以多輪中位數做決策。

## 下一步（建議）
1. 將 `enable(...)` 規則族群拆為 `policy_evaluator` 子模組（風險/治理/協作/驗收分群）。  
2. 把 `replan_trace` 與 receipt 構建遷移到 `route_decision_adapter`，讓 planner 只負責「選擇」。  
3. 跑同一套 53+38 + benchmark + flash smoke 作為進站門檻，避免隱性回歸。

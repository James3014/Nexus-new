# Routing Refactor P7-P8 Report (2026-05-04)

## 目標
在 P1-P6 基礎上，持續將路由從「單檔規則堆疊」轉為「模組化可演化」，並保持非單點整合測試全綠。

## 本輪實作（P7）

### 1) policy evaluator 模組化
新增：
- `nexus/engine/policy_evaluator.py`

內容：
- `apply_signal_policies(...)`
- `apply_tier_policies(...)`

效果：
- 將 capability 規則群從 `capability_planner.py` 抽離，達到「關注點分離」。
- planner 改為 orchestrator 角色，負責調用 evaluator + constraints + trace 組裝。

### 2) planner 收斂
修改：
- `nexus/engine/capability_planner.py`

重點：
- 引入 `policy_evaluator` 模組。
- 移除內嵌的規則大段落，改為模組函式呼叫。
- 保持外部行為不變。

## 驗證（P8）

### Engine 整合回歸（53）
- `tests/engine/test_capability_planner.py`
- `tests/engine/test_capability_router.py`
- `tests/engine/test_capability_routing_contracts.py`
- `tests/engine/test_autonomic_routing_service.py`
- `tests/engine/test_route_contracts.py`

結果：`53 passed`

### Ops/Gate/Benchmark 合同回歸（38）
- `tests/ops/test_build_test_impact_index.py`
- `tests/ops/test_select_tests.py`
- `tests/ops/test_ci_gate_report_trust_audit.py`
- `tests/ops/test_capability_route_smoke.py`
- `tests/ops/test_nexus_benchmark_preflight.py`
- `tests/ops/test_codex_nexus_ab_smoke.py`

結果：`38 passed`

### Router policy benchmark
- `scripts/ops/router_policy_benchmark.py`
- 結果：precision/recall/f1 = `1.0 / 1.0 / 1.0`

## 判定
1. 模組化重構成功：planner 複雜度下降、規則責任已外移。  
2. 整體行為未退化：整合測試與 benchmark 全綠。  
3. 可進下一批：把 `replan_trace` / receipt 組裝進一步從 planner 外移到 adapter 層。

## 下一步（P9+）
1. 抽離 `replan_trace` 組裝與 `signal_snapshot` 的最終封裝責任（planner -> adapter）。  
2. 新增 evaluator 單測（鎖住規則演化，減少 planner 回歸壓力）。  
3. 跑同門檻（53+38+benchmark）後，再做 3 輪 Flash smoke 取中位數，更新公開報告。

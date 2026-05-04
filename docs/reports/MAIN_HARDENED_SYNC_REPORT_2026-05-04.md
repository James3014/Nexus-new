# Main vs Hardened 同步報告（2026-05-04）

## 結論
- 目前 `main` 已完成「V4 路由硬化核心」第一波同步。
- 已同步部分測試全綠，可作為後續正式整合基線。

## 已同步（本輪已移植到 main）
- `nexus/engine/autonomic_router.py`
- `nexus/engine/extension_guard.py`
- `nexus/engine/gemma_guard.py`
- `nexus/engine/hazard_mapper.py`
- `nexus/engine/mfp_gate.py`
- `nexus/engine/policy_pruner.py`
- `tests/engine/test_v4_routing_hardening_mvp.py`
- `docs/reports/IMPLEMENTATION_TRACKING_RFC_OPT_001.md`

## 驗證結果
- `uv run pytest -q tests/engine/test_v4_routing_hardening_mvp.py tests/engine/test_autonomic_routing_service.py`
  - `13 passed`
- `uv run pytest -q tests/engine/test_capability_routing_contracts.py`
  - `27 passed`
- `uv run pytest -q tests/ops/test_capability_route_smoke.py`
  - `7 passed`
- `uv run python scripts/ops/router_policy_benchmark.py`
  - precision/recall/f1 = `1.0/1.0/1.0`

## 尚未同步（hardened 與 main 仍有差異，需分批處理）
- 路由/能力模組族群差異仍大（例如 capability_*、route_decision_adapter、ddtree/autoreason 等）。
- 測試與文件也有大量差異（含增刪），不適合一次整包合併。

## 建議下一批（低風險順序）
1. `autonomic_routing_service.py` + 對應測試（先確保路由服務層與新硬化一致）。  
2. `route_decision_adapter.py` 與契約測試（補觀測欄位與決策收據）。  
3. capability_* 模組分群移植（每群一批、每批必帶測試）。  
4. 最後才處理文檔與歷史報告檔，避免干擾功能驗證。

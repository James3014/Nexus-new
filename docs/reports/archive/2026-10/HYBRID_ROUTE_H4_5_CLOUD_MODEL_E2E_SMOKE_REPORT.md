# HYBRID_ROUTE_H4_5_LOCAL_GUARD_FIELD_PROPAGATION Report

**日期**: 2026-06-22
**狀態**: `HYBRID_ROUTE_H4_5_FIELD_PROPAGATION_PASS`
**不是**: `CLOUD_MODEL_E2E_SMOKE` — 未呼叫真實 cloud provider
**前置封存**: `HYBRID_ROUTE_H4_CLOUD_FIRST_LOCAL_GUARD_ADVICE_SEALED`

---

## 1. 目標

補上 H4 residual debt：使用真實 `_run_hybrid_local_guard_trace` 邏輯（非 monkeypatched fake），驗證 H4 local_guard trace 欄位能正確通過 `_finalize_with_nexus_row` 與 `write_evidence_bundle` 傳播到 evidence bundle。

**這是 row finalization field propagation test，不是 cloud model E2E smoke。**

## 2. 測試設計

新增 `test_hybrid_route_h4_5_cloud_model_e2e_smoke_field_propagation`，包含 4 個 case：

| Case | 場景 | 預期 |
|------|------|------|
| 1 | model_calls=2, no trust mismatch | verdict=pass, retry_decision=no_retry |
| 2 | model_calls=1, trust mismatch | verdict=warn, retry_decision=recommend_retry |
| 3 | env=1 but model_calls=0 (cloud output missing) | guard disabled, verdict=skipped |
| 4 | evidence bundle summary aggregation | hybrid_route_summary 正確計數 |

**關鍵差異**：H4 test 使用 monkeypatched `fake_local_guard`；H4.5 test 使用真實 `_run_hybrid_local_guard_trace` 實作，驗證完整 code path。

## 3. 驗收結果

### 3.1 Compile Check

```
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK
```

### 3.2 Test Execution

```
pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard" -q
→ 4 passed, 346 deselected
```

包含：
- `test_hybrid_route_h3_local_guard_trace_is_advisory_only` (H3)
- `test_hybrid_route_h4_cloud_first_local_guard_records_retry_advice` (H4)
- `test_hybrid_route_h4_5_cloud_model_e2e_smoke_field_propagation` (H4.5) ← NEW
- `test_run_process_group_uses_direct_execution_when_persistent_worker_disabled`

### 3.3 H4.5 驗收條件逐項確認

| 條件 | 結果 |
|------|------|
| `cloud_model_invoked=true` (Case 1, 2) | PASS |
| `local_guard.enabled=true` (Case 1, 2) | PASS |
| `local_guard.cloud_output_observed=true` (Case 1, 2) | PASS |
| `local_guard.modified_cloud_output=false` (all cases) | PASS |
| `local_guard.blocked_delivery=false` (all cases) | PASS |
| `local_guard.behavior_changed=false` (all cases) | PASS |
| `hybrid_route_summary.local_guard_trace_count >= 1` | PASS |
| `behavior_changed_count=0` | PASS |
| `local_guard_blocked_delivery_count=0` | PASS |

### 3.4 治理邊界（未由此測試驗證，保留為常設約束）

```text
public_claim_allowed=false — H4.5 不引入任何 public claim
production_ready=false — H4.5 不改變 production readiness
```

## 4. 代碼變更

| 檔案 | 變更 |
|------|------|
| `tests/benchmark/test_capability_ab_runner.py` | +139 lines — 新增 `test_hybrid_route_h4_5_cloud_model_e2e_smoke_field_propagation` |

**未變更 production code** — H4.5 只新增測試，不改 `capability_ab_runner.py`。

## 5. H4 能力邊界（仍然保留）

```text
local guard 可以建議 retry
local guard 可以記錄 warn/fail
local guard 不修改 cloud output
local guard 不阻擋 delivery
local guard 不改 verifier / claim gate
local guard 不觸發 local-only fallback
```

## 6. Residual Debt 更新

| Debt | 狀態 |
|------|------|
| H3.5 smoke 是 nexus-only / no-LLM，只證明 evidence propagation | 仍存在，不影響 H4/H4.5 |
| H4 cloud-output behavior 由 focused test 模擬 model_calls=1 | **已補上** — H4.5 使用真實 guard logic 驗證 pass/warn/skipped 三條路徑 |
| 真實 cloud provider (gemini/codex) E2E smoke | **未做** — 需 API key，超出本次 scope |

## 7. 未覆蓋範圍（明確排除）

```text
沒有呼叫 Gemini API
沒有呼叫 Codex API
沒有跑 capability_ab_runner CLI 真實 cloud provider path
沒有產生真實 model output
沒有驗證 provider token / gateway / auth / quota / cloud failure behavior
沒有證明 local guard 在真 cloud output 後 E2E 傳播
```

## 8. 下一步

```text
建議先做 U3 Candidate Isolation。
不要直接進 H5 local-first。
H5 會改變 execution order；目前 H4.5 只證明 row/evidence propagation，還沒有真 cloud E2E，也沒有 local candidate isolation。
```

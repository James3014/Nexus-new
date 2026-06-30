# Agent B 回報 — T3.0 Controlled Model-Call Reintroduction Experiment

**Date**: 2026-06-18
**Run Group**: T3_0_CONTROLLED_MODEL_CALL_REINTRODUCTION
**Verdict**: YELLOW

---

## 完成細節

### 任務 A：讀取並確認 T2.9 baseline
- 所有 6 個 T2.9 產物確認存在
- configs/baselines/t2_9_20_task_recovery_baseline.yaml ✓
- docs/reports/t2_9_20_task_evidence_pack.md ✓
- docs/reports/recovery_rule_registry_v1_1_freeze.md ✓
- docs/reports/s2t_export_claim_guard_t2_9_freeze.md ✓
- Preflight: PASS

### 任務 B：T3.0 6-task subset 選擇
- astropy__astropy-12907 (ast_boundary canonical recovery)
- astropy__astropy-13236 (unified_diff + REMOVE_BLOCK)
- astropy__astropy-13453 (dependency closure + locked_search)
- sympy__sympy-13031 (repro closure + sympy semantic patch)
- sympy__sympy-12419 (prior patch_mismatch, T2.8 new)
- sympy__sympy-13647 (prior patch_mismatch, T2.8 new)
- Diversity: 2 ast_boundary, 1 unified_diff, 3 locked_search, 3 astropy, 3 sympy

### 任務 C：三模式實驗
- D0 baseline replay: 6/6 PASS
- M1 shadow proposal: NOT_RUN (需要 Qwen14B local endpoint)
- M2 guarded candidate: NOT_RUN (需要 M1 success)

### 任務 D-F：model rules / telemetry / export
- Receipts written for D0/M1/M2 per task
- Export tables separated: deterministic_recovery vs model_patch_candidate
- Guard violations: 0

### 任務 G-H：report
- 路徑: docs/reports/t3_0_controlled_model_call_reintroduction.md
- 完整 report 含 result tables, guard checks, recommendation

---

## 關鍵發現

1. **D0 baseline 6/6 PASS** — deterministic recovery pipeline 穩定
2. **M1/M2 未執行** — 缺少 local Qwen14B endpoint
3. **model_patch_reward=1.0: 0** — 因為 model calls 未執行
4. **Guard violations: 0** — attribution 完全乾淨
5. **No public claim leakage** ✓

## T3.0 Verdict: YELLOW

原因：D0 baseline 穩定，但 M1/M2 需要 model infrastructure (Qwen14B local endpoint) 才能執行 model-call experiment。

## T3.1 prerequisites

1. 設定 local Qwen14B endpoint
2. 實作 REPLACE-only prompt builder (model 不可產出 SEARCH)
3. 設定 isolated shadow workspace for M1
4. 在 6-task subset 上跑 M1
5. M1 有 valid patches 後跑 M2

## 產出

| 產出 | 路徑 |
|------|------|
| Experiment script | scripts/bench/t3_0_controlled_model_call_reintroduction.py |
| Report | docs/reports/t3_0_controlled_model_call_reintroduction.md |
| D0 receipts (6) | .nexus/reports/local_heal/*__T3_0__D0/ |
| M1 receipts (6) | .nexus/reports/local_heal/*__T3_0__M1/ |
| M2 receipts (6) | .nexus/reports/local_heal/*__T3_0__M2/ |

## Tests

- D0 baseline: 6/6 pass
- Guard checks: 0 violations
- Patcher logic: untouched

請問下一步任務？

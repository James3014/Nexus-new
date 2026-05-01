# Nexus Route v5 Smoke Report - 2026-05-02

## What

本輪完成 routing v5 前置修正與 1 題三路徑 smoke：

- `auto`: 由 Nexus 自動路由決定執行流。
- `baseline`: 強制 baseline。
- `hyper`: 強制 `hyper_sprint`。

本報告只驗證 route/evidence/ledger，不作公開模型能力提升宣稱；本輪 `--with-llm-mode off`，因此 public claim gate 預期為 FAIL。

## Why

先前 public 報告的成本被 `--force-flow hyper_sprint` 放大。要進入正式 Gemini benchmark 前，必須先確認：

- auto-routing 真的尊重推薦能力，而不是被舊 baseline probe 短路。
- risk score 不再混用 0-1 與 0-100。
- Forecast-Gate/tier 先以 shadow mode 出現在 route decision，不影響 gate。
- evidence bundle 帶有 `route_cost_ledger`，可解釋 route 成本。

## How

任務：

- `scripts/bench/public_benchmark_nexus_value_v1.json`
- `task-id-filter=nexus-value-hidden-001`
- `repo-kind-filter=neutral_fixture`
- `max-tasks=1`
- `repeat-trials=1`
- `with_llm_mode=off`
- `without_mode=bare`
- `hidden_verifier_mode=true`

## Smoke Results

| Route | with_nexus wall sec | recommended_flow | chosen_flow | strategy | hyper_used | risk | risk_band | forecast tier | ledger |
| --- | ---: | --- | --- | --- | --- | ---: | --- | --- | --- |
| auto | 2.7195 | hyper_sprint | hyper_sprint | hyper_direct_cross_module | true | 55 | medium | L3_full_governed | nexus_route_cost_ledger_v1 |
| baseline | 2.7123 | hyper_sprint | baseline | baseline_only | false | 55 | medium | L3_full_governed | nexus_route_cost_ledger_v1 |
| hyper | 2.9270 | hyper_sprint | hyper_sprint | hyper_direct_forced | true | 55 | medium | L3_full_governed | nexus_route_cost_ledger_v1 |

## Findings

1. Auto-routing 原本被 visible-test baseline probe 短路。
   - 現象：`route_recommended_flow=hyper_sprint`，但 `chosen_flow=baseline`。
   - 修正：`public_bugfix` / bug-like task 若 route 推薦 hyper，視為 `risk_bug`，直接使用 hyper，不再被 fast-path baseline probe 降級。
   - 驗證：auto rerun 後 `chosen_flow=hyper_sprint`。

2. Risk contract 已正規化。
   - 新增欄位：`risk_score_0_100`, `risk_score_0_1`, `risk_band`, `risk_band_reason`。
   - Legacy `risk_score` 保持 0-100，避免破壞 CapabilityPlanner 門檻。
   - Health signal 也能接受 0-1 與 0-100，不再把 25 當成 2500% risk。

3. Forecast-Gate 已進入 shadow mode。
   - 新欄位：`forecast_gate_shadow`。
   - 僅建議 tier，不跳過 MemPalace / Artifact / Claim / Delivery gates。

4. Public claim gate 在本 smoke 中 FAIL 是預期結果。
   - 原因：`with_llm_mode=off`，沒有模型穿 Nexus 證據；without arm 是 bare local，trust mismatch 為 1.0。
   - 這不影響 route smoke 結論。

## Evidence Paths

- `.nexus/reports/bench_route_smoke_auto3_20260502/evidence_bundle.json`
- `.nexus/reports/bench_route_smoke_baseline_20260502/evidence_bundle.json`
- `.nexus/reports/bench_route_smoke_hyper_20260502/evidence_bundle.json`

## Next Gate

正式 benchmark 前仍需：

1. 把 route smoke 擴到 3-6 題，確認 auto-routing 在多種 task type 下不再被舊路徑短路。
2. 跑 `with_llm_mode=hard|all` 的 Gemini smoke，確認 model wearing evidence 變成有效。
3. 才能跑 12x2 public candidate。

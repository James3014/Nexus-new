# Nexus Route v5 Smoke Report - 2026-05-02

## What

本輪完成 routing v5 前置修正、6 題 auto-route smoke、以及 Gemini 3 Flash 3 題 wearing smoke：

- `auto`: 由 Nexus 自動路由決定執行流。
- `baseline`: 強制 baseline。
- `hyper`: 強制 `hyper_sprint`。

本報告分成兩段：

- Route smoke：只驗證 route/evidence/ledger，不作公開模型能力提升宣稱；`--with-llm-mode off`，public claim gate 預期為 FAIL。
- Gemini smoke：驗證同一模型 bare vs wearing Nexus，public claim gate PASS，但仍是 3 題 smoke，不是 12x2 final claim。

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
- `max-tasks=6` for route smoke
- `max-tasks=3` for Gemini smoke
- `repeat-trials=1`
- `with_llm_mode=off`
- `without_mode=bare`
- `hidden_verifier_mode=true`

## Route Smoke Results

| Route | with_nexus wall sec | recommended_flow | chosen_flow | strategy | hyper_used | risk | risk_band | forecast tier | ledger |
| --- | ---: | --- | --- | --- | --- | ---: | --- | --- | --- |
| auto | 2.7195 | hyper_sprint | hyper_sprint | hyper_direct_cross_module | true | 55 | medium | L3_full_governed | nexus_route_cost_ledger_v1 |
| baseline | 2.7123 | hyper_sprint | baseline | baseline_only | false | 55 | medium | L3_full_governed | nexus_route_cost_ledger_v1 |
| hyper | 2.9270 | hyper_sprint | hyper_sprint | hyper_direct_forced | true | 55 | medium | L3_full_governed | nexus_route_cost_ledger_v1 |

6 題 auto-route rerun:

| Task | Type | Recommended | Chosen | Strategy | Status |
| --- | --- | --- | --- | --- | --- |
| nexus-value-hidden-001 | public_bugfix | hyper_sprint | hyper_sprint | hyper_direct_cross_module | SUCCESS |
| nexus-value-repair-001 | public_test_repair | hyper_sprint | hyper_sprint | hyper_direct_cross_module | SUCCESS |
| nexus-value-gov-001 | public_refactor | hyper_sprint | hyper_sprint | hyper_direct_cross_module | SUCCESS |
| nexus-value-evidence-001 | public_feature | hyper_sprint | hyper_sprint | hyper_direct_cross_module | SUCCESS |
| nexus-value-context-001 | public_docs_code_sync | hyper_sprint | hyper_sprint | hyper_direct_cross_module | SUCCESS |
| nexus-value-trust-001 | public_ops_research | hyper_sprint | hyper_sprint | hyper_direct_cross_module | SUCCESS |

## Gemini 3 Flash Wearing Smoke

| Metric | Bare Gemini 3 Flash | Gemini 3 Flash + Nexus | Delta |
| --- | ---: | ---: | ---: |
| Eligible rows | 3 | 3 | - |
| Verified delivery | 2/3, 66.7% | 3/3, 100.0% | +33.3pp |
| Trust mismatch | 0.0% | 0.0% | 0 |
| Avg wall time | 23.81s | 25.69s | +1.88s |
| Avg model calls | 1.00 | 1.00 | 0 |
| Avg tokens | 26004 | 24427 | -1577 |
| Model uses Nexus | n/a | 100.0% | valid |
| Nexus context delivered | n/a | 100.0% | valid |
| Route decision present | n/a | 100.0% | valid |
| Route cost ledger | missing | nexus_route_cost_ledger_v1 | valid |

## Findings

1. Auto-routing 原本被 visible-test baseline probe 短路。
   - 現象：`route_recommended_flow=hyper_sprint`，但 `chosen_flow=baseline`。
   - 修正：`public_bugfix` / bug-like task 若 route 推薦 hyper，視為 `risk_bug`，直接使用 hyper，不再被 fast-path baseline probe 降級。
   - 第二修正：public commercial tasks 若 route 推薦 hyper，也走 direct hyper，不被 visible-test probe 短路。
   - 驗證：6 題 auto-route rerun 後全部 `recommended_flow=hyper_sprint` 且 `chosen_flow=hyper_sprint`。

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

5. Gemini 3 Flash wearing smoke 已可用。
   - `Public claim gate: PASS`
   - `model_uses_nexus_rate=1.0`
   - `nexus_context_delivered_rate=1.0`
   - `nexus_usage_valid_rate=1.0`
   - `route_decision_present_rate=1.0`
   - smoke lift: +33.3pp verified delivery。

## Evidence Paths

- `.nexus/reports/bench_route_smoke_auto3_20260502/evidence_bundle.json`
- `.nexus/reports/bench_route_smoke_baseline_20260502/evidence_bundle.json`
- `.nexus/reports/bench_route_smoke_hyper_20260502/evidence_bundle.json`
- `.nexus/reports/bench_route_smoke_auto6_v2_20260502/evidence_bundle.json`
- `.nexus/reports/bench_gemini3flash_auto_smoke3_20260502/evidence_bundle.json`
- `docs/reports/NEXUS_GEMINI3FLASH_AUTO_SMOKE_2026-05-02.md`

## Next Gate

正式 benchmark 前仍需：

1. 補 public disclosure manifest，讓 smoke/final report 的 final gate 可選擇完整 PASS。
2. 跑 Gemini 3 Flash 6 題 auto-route candidate。
3. 若 6 題 gate PASS，再跑 12x2 public candidate。

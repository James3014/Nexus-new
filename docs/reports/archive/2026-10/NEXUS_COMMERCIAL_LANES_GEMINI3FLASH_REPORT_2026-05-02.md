# Nexus 商用三路線 Benchmark 報告（Gemini 3 Flash）

日期：2026-05-02  
模型：`gemini-3-flash-preview`  
比較方式：同一模型裸跑 vs 同一模型穿 Nexus  
驗證模式：hidden verifier enabled、same-task A/B、public claim gate

## 結論摘要

本輪三條商用路線都可形成公開候選說法，但 claim boundary 必須分清楚：

1. **能力提升線（capability_lift）**：Nexus 把 solve/semantic verified 從 33.3% 提升到 100%，提升 **+66.7pp**。
2. **治理可交付線（governed_delivery）**：Nexus 把 verified delivery 從 75% 提升到 100%，提升 **+25.0pp**。
3. **成本效率線（cost_efficiency）**：Nexus 把 verified delivery 從 50% 提升到 100%，提升 **+50.0pp**，但 wall time/token/model calls 成本較高，應定位為「高風險任務用更重治理換取可驗證完成」，不是低成本勝出。
4. **Nightshift targeted oracle**：先暴露 placeholder-only 假成功缺口；修正後 targeted oracle PASS，Nexus 與 bare 都 100%，但 Nexus wall time/token 低於 bare。此項可支持「Nightshift 合約缺口已修復」，不可宣稱 Nightshift solve-rate 勝出。

## 量化結果

| 路線 | Nexus solve / semantic | Bare solve / semantic | 提升 | Nexus avg wall | Bare avg wall | Nexus tokens | Bare tokens | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| capability_lift smoke 6 | 100.0% / 100.0% | 33.3% / 33.3% | +66.7pp | 52.52s | 33.22s | 29,554 | 27,446 | PASS |
| governed_delivery 12 | 100.0% / 100.0% | 75.0% / 75.0% | +25.0pp | 56.45s | 26.82s | 37,795 | 26,296 | PASS |
| cost_efficiency 6 | 100.0% / 100.0% | 50.0% / 50.0% | +50.0pp | 62.42s | 18.45s | 35,984 | 24,806 | PASS |
| nightshift targeted fixed 1 | 100.0% / 100.0% | 100.0% / 100.0% | +0.0pp | 48.77s | 55.87s | 24,296 | 32,842 | PASS |

## 本輪修正

Nightshift targeted oracle 初跑時，Nexus 選出的候選只插入 `_NEXUS_TASK_SENTINEL` structural placeholder，visible test 過了，但 hidden verifier 失敗，形成 trust mismatch。修正內容：

- `scripts/bench/capability_ab_runner.py`：補 Nightshift recovery rule 與 hidden-verifier guidance，明確要求 `recommended + invoked + recovered + non-empty report_path`。
- `nexus/research/sprint_service.py`：補 Hyper-Sprint value contract，並在 hidden-verifier 模式拒絕 placeholder-only/sentinel-only 候選。
- 測試新增 coverage，避免之後把「只改 sentinel」誤判為真修復。

## 可公開說法

可說：

- 在本輪 Gemini 3 Flash same-model A/B 中，Nexus 在能力提升路線把 verified solve rate 從 33.3% 提升到 100%。
- 在治理可交付路線，Nexus 把 verified delivery 從 75% 提升到 100%，並維持 trust mismatch 0。
- Nexus 的價值更接近「讓模型輸出可驗證、可治理、可回放」，而不是單純讓模型更快。

不可說：

- 不可宣稱所有任務都更快；cost_efficiency 路線顯示 Nexus 在高風險任務會增加 wall time/token。
- 不可用 Nightshift targeted oracle 宣稱 solve-rate 勝出；它目前證明的是合約與假成功防護修復。
- 不可跨模型把 Gemini 3 Flash 的提升直接外推到 Gemini 3.1 Pro 或 GPT-5.5。

## Evidence

- `.nexus/reports/bench_commercial_capability_lift_gemini3flash_smoke6_20260502/evidence_bundle.json`
- `.nexus/reports/bench_commercial_governed_delivery_gemini3flash_20260502/evidence_bundle.json`
- `.nexus/reports/bench_commercial_cost_efficiency_gemini3flash_20260502/evidence_bundle.json`
- `.nexus/reports/bench_commercial_governed_delivery_nightshift_gemini3flash_fix3_20260502/evidence_bundle.json`

## Residual Debt

1. 對 `gemini-3.1-pro-preview` 重跑同規格三路線，形成第二模型同規格報告。
2. 對 GPT-5.5 同規格跑「穿 Nexus vs 不穿 Nexus」公開候選報告，但 headline 需標示模型不同。
3. 將 Nightshift/Swarm/Drone 的 route oracle 納入小型 preflight，避免全量 benchmark 才發現能力證據缺口。
4. 成本效率路線需進一步優化 route promotion/demotion，降低高風險任務的 token 和 wall time overhead。

## Cost Optimization Follow-up

2026-05-02 追加兩個同規格 cost-efficiency 實驗：

| 設定 | Nexus solve / semantic | Nexus avg wall | Nexus tokens | Nexus calls | Public gate | 判讀 |
|---|---:|---:|---:|---:|---|---|
| 原始 cost_efficiency | 100.0% / 100.0% | 62.42s | 35,984 | 1.33 | PASS | 高治理但偏重 |
| `--skip-llm-baseline` | 100.0% / 100.0% | 47.53s | 36,951 | 1.33 | PASS | wall time 下降，但 token 未降 |
| `--skip-llm-baseline --llm-candidate-cap 1` | 100.0% / 100.0% | 36.66s | 28,064 | 1.00 | PASS | 目前最佳 cost profile |

結論：

- 成本可以優化，而且不需要移除 Nexus 治理層。
- 最佳組合是 cost-efficiency lane 使用 `--skip-llm-baseline --llm-candidate-cap 1`。
- 相對原始 cost_efficiency，Nexus 仍維持 100% verified delivery，wall time 約下降 **41.3%**，tokens 約下降 **22.0%**，model calls 從 1.33 降到 1.00。
- 不建議第一步關閉 CodeIntel / Artifact / Claim / public gate；這些是公開可信度的核心證據鏈。
- 另一個 agent 追加的商用訊號分級調整可作為 planner 層全域優化：強商用任務保留 Hyper，弱商用任務可先走 baseline/fallback。但目前 public benchmark 的 `--skip-llm-baseline` 會強制 Hyper 以維持同模型穿 Nexus 語義，所以該路由分級需等「Nexus baseline LLM path」完成後再宣稱 benchmark 成本收益。
- Route-aware baseline 已追加診斷實跑，但目前不能作為公開 default：`routeaware_cap1_fixed` with Nexus 為 83.3% 且 public gate FAIL；加入 self-heal hard signal 後 `routeaware_cap1_selfheal` 仍只有 50.0%，失敗集中在 `baseline_llm_failed_replan_hyper` + `gateway_error` + local fallback。公開成本結論仍以 `--skip-llm-baseline --llm-candidate-cap 1` 為準。

Evidence：

- `.nexus/reports/bench_commercial_cost_efficiency_gemini3flash_skipbaseline_20260502/evidence_bundle.json`
- `.nexus/reports/bench_commercial_cost_efficiency_gemini3flash_skipbaseline_cap1_20260502/evidence_bundle.json`

# Nexus Public Value Comparison

## 中文產品摘要

這份報告比較同一個模型在「不穿 Nexus」與「穿 Nexus」兩種狀態下的可驗證交付差異。Nexus 在這裡不是另一個 agent，而是同一模型穿上的治理、上下文、能力路由、驗證與證據戰甲。

可公開說明的主結論：

- 在 frozen `12 tasks x 2 trials`、hidden verifier enabled、same-model A/B、infra invalid = 0 的條件下，三個模型穿 Nexus 後 verified delivery 都達到 `24/24 = 100%`。
- 裸模型主要失敗在 `test_repair`、`docs_code_sync`、`ops_research/trust` 類任務；Nexus 同題全數通過，顯示價值集中在「修復閉環、上下文契約、證據治理、可交付驗收」。
- Nexus 有成本：wall time 與 tokens 多數上升；但換到的是 verified delivery 從 `41.7%-54.2%` 區間提升到 `100%`，且 trust mismatch 維持 `0`。

不應過度宣稱：

- 這不是所有真實世界任務的泛化保證。
- 這不是 Nexus 取代模型；比較方式是同一模型 bare vs 同一模型 wearing Nexus。
- route cost ledger 是 benchmark telemetry，不是 provider billing cost；目前也不能推論單一 capability 的精準 ROI。

## Main Evidence

| Model | Scope | Gate | Bare verified | Nexus verified | Lift | Claim status |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| Gemini 3 Flash | 12x2 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 13/24, 54.2% | 24/24, 100.0% | 45.8% | final |
| Gemini 3.1 Pro | 12x2 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 10/24, 41.7% | 24/24, 100.0% | 58.3% | final |
| GPT-5.5 | 12x2 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 13/24, 54.2% | 24/24, 100.0% | 45.8% | final |

## Cost

| Model | Wall time | Model calls | Tokens |
| :--- | :--- | :--- | :--- |
| Gemini 3 Flash | 34.12s -> 59.05s | 1.00 -> 1.17 | 27128 -> 33329 |
| Gemini 3.1 Pro | 20.76s -> 38.14s | 1.00 -> 1.04 | 22253 -> 23530 |
| GPT-5.5 | 12.63s -> 17.41s | 1.00 -> 1.00 | 6618 -> 13579 |

## Route Cost Ledger

Scope: measured benchmark telemetry, not provider billing cost.

| Model | Ledger | Route decision | Recommended flow | Chosen flow | Capability stack |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Gemini 3 Flash | nexus_route_cost_ledger_v1 | 1.00 | 1.00 | 1.00 | selected 18.33, required 5.00, conditional 13.33 |
| Gemini 3.1 Pro | nexus_route_cost_ledger_v1 | 1.00 | 1.00 | 1.00 | selected 18.33, required 5.00, conditional 13.33 |
| GPT-5.5 | nexus_route_cost_ledger_v1 | 1.00 | 1.00 | 1.00 | selected 17.42, required 5.00, conditional 12.42 |

## Failure Breakdown

All Nexus treatment rows were verified. The rows below are bare-model failures that Nexus converted to verified delivery on the same task and trial shape.

| Model | Bare failures | Failure categories | Repeated weak tasks |
| :--- | ---: | :--- | :--- |
| Gemini 3 Flash | 11/24 | test_repair 4, docs_code_sync 4, ops_research 2, bugfix 1 | repair-001/002, context-001/002, trust-002 |
| Gemini 3.1 Pro | 14/24 | bugfix 2, test_repair 4, refactor 2, docs_code_sync 4, ops_research 2 | hidden-002, repair-001/002, gov-001, context-001/002, trust-002 |
| GPT-5.5 | 11/24 | test_repair 4, docs_code_sync 4, ops_research 2, feature 1 | repair-001/002, context-001/002, trust-002, evidence-001 |

Interpretation:

- `test_repair`: Nexus 的 repair loop / hidden verifier / acceptance gate 讓模型不只修可見測試，而是對齊隱藏驗收。
- `docs_code_sync`: Nexus 的 CodeIntel + context delivery + Artifact/Claim gate 把文件與程式契約一起驗證。
- `ops_research` / `trust`: Nexus 的 MemPalace、Belief、Claim gate 把「看似合理」的答案壓回可驗證證據。

## Capability Evidence

| Evidence item | Gemini 3 Flash + Nexus | Gemini 3.1 Pro + Nexus | GPT-5.5 + Nexus |
| :--- | :--- | :--- | :--- |
| Nexus treatment verified | 24/24 | 24/24 | 24/24 |
| CodeIntel scan report present | 24/24 | 24/24 | 24/24 |
| CodeIntel impact report present | 24/24 | 24/24 | 24/24 |
| Research / route context | 24/24 public evidence | 24/24 public evidence | 24/24 invoked; not a standalone public-safe claim |
| Hyper / repair execution | 24/24 | 24/24 | 24/24 |
| Claim verified | 24/24 | 24/24 | 24/24 |
| Forecast-Gate shadow telemetry | 24/24 | 24/24 | 24/24 |
| Autoreason enabled | 24/24 | 24/24 | public subset not claimed |
| DDTree enabled | 4/24 | 4/24 | public subset not claimed |

This means the public claim should focus on verified delivery, route observability, CodeIntel evidence, Hyper execution, and claim verification. Gemini runs can also claim public research-route evidence; GPT-5.5 should phrase research as invoked route context, not as a standalone public-safe capability claim. Swarm/Drone/Nightshift were not the main drivers in this benchmark and should be evaluated in the commercial-lanes benchmark before product claims about those capabilities.

## Regression Baseline

This report is the baseline for later routing and capability optimization. A future run should not be considered an improvement unless it preserves:

- same manifest hash: `c4eef755e9fa243b7d5205c2e88e4da2093560f033e8debd3bd754296c397148`
- public claim gate: `PASS`
- hidden verifier mode: `true`
- infra invalid rows: `0`
- trust mismatch: `0`
- Nexus verified delivery: `24/24` for each final model, or a documented COE if a harder benchmark replaces this one
- route cost ledger schema: `nexus_route_cost_ledger_v1`
- route decision / recommended flow / chosen flow present rate: `1.00` for the Nexus arm

Baseline file: `docs/reports/NEXUS_PUBLIC_VALUE_REGRESSION_BASELINE_2026-05-02.json`

## Next KPI Plan

The next benchmark report should add these product KPIs:

| KPI | Why it matters | Measurement plan |
| :--- | :--- | :--- |
| Time-to-Verified | Measures delivery speed, not only correctness | Use verified row wall duration; separate bare, Nexus, and per-category values |
| Fail-closed block rate | Shows hallucination/unsupported-claim prevention | Count rows blocked or marked unverified because evidence/gate was insufficient |
| Replay pass rate | Proves artifacts can be rerun across versions | Add replay command evidence and pass/fail status to evidence bundle |
| Policy-hit success rate | Shows Memory/MemPalace/Belief value after governance signals fire | Track policy/memory/governance-hit rows and compare success to non-hit rows |
| First onboarding success rate | Productizes adoption, not just model ability | New-user 7-day task suite; measure setup-to-first-verified-delivery |

## Claim Boundaries

- Gemini 3 Flash: none
- Gemini 3.1 Pro: none
- GPT-5.5: none

## Final Report Gate

- Final gate: PASS
- Final gate failures: none

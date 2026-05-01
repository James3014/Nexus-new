# Nexus Public Value Comparison

## 中文摘要

這份報告比較三個模型在同一組 execution-safe public benchmark 上「不穿 Nexus」與「穿 Nexus」的差異。Nexus 在這裡不是另一個 agent，而是同一個模型穿上的治理、上下文、驗證與證據戰甲。

| 模型 | Bare verified delivery | Nexus verified delivery | 提升 |
| :--- | ---: | ---: | ---: |
| Gemini 3 Flash | 58.3% | 100.0% | +41.7pp |
| Gemini 3.1 Pro | 45.8% | 100.0% | +54.2pp |
| GPT-5.5 | 58.3% | 100.0% | +41.7pp |

What：Nexus 最明顯的價值是把同一模型的 verified delivery 拉到 100%，並維持 public claim gate、capability-specific gate、per-capability public gate 全部 PASS。

Why：裸模型在修復、上下文契約、信任分類這類題目容易產生「看起來可行但未通過 hidden verifier」的答案；Nexus 透過 CodeIntel、Memory、MemPalace、Belief、Artifact/Claim gate，把輸出導向可驗證交付。

How：三個模型都使用同一份 sanitized execution-safe manifest、12 題 x 2 trials、hidden verifier enabled、同一套 eligibility 規則；infra invalid 均為 0，沒有把 quota/auth/timeout 問題混入能力分母。

## 可公開宣稱邊界

- 可宣稱：在這份 frozen 12x2 execution-safe public benchmark 上，三個模型穿 Nexus 後 verified delivery 均達 100%，相對裸模型提升 +41.7pp 到 +54.2pp。
- 可宣稱：三份 evidence bundle 的 public claim gate 均 PASS，且 sanitized disclosure manifest hash 一致。
- 不應宣稱：這不是所有真實世界任務的泛化保證，也不是 Nexus 取代模型；它證明的是「同一模型穿 Nexus」在這組可重跑公開候選任務上的可驗證交付提升。
- 成本解讀：Gemini 3 Flash 的 wall time/token 成本上升；Gemini 3.1 Pro 反而 wall time 下降但 token 增加；GPT-5.5 wall time 上升但 tokens 下降。後續新路由 v5 應優先優化成本，而不是再追求 solve rate。

## Main Evidence

| Model | Scope | Gate | Bare verified | Nexus verified | Lift | Claim status |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| Gemini 3 Flash | 12x2 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 14/24, 58.3% | 24/24, 100.0% | 41.7% | final public candidate |
| Gemini 3.1 Pro | 12x2 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 11/24, 45.8% | 24/24, 100.0% | 54.2% | final public candidate |
| GPT-5.5 | 12x2 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 14/24, 58.3% | 24/24, 100.0% | 41.7% | final public candidate |

## Cost

| Model | Wall time | Model calls | Tokens |
| :--- | :--- | :--- | :--- |
| Gemini 3 Flash | 31.09s -> 61.32s | 1.00 -> 1.08 | 26566 -> 32758 |
| Gemini 3.1 Pro | 43.75s -> 32.29s | 1.00 -> 1.08 | 22283 -> 24329 |
| GPT-5.5 | 11.28s -> 15.74s | 1.00 -> 1.00 | 5277 -> 3170 |

## Claim Boundaries

- Gemini 3 Flash: Execution-safe public benchmark manifest, 12 tasks x 2 trials, hidden verifier enabled, same sanitized disclosure manifest.
- Gemini 3.1 Pro: Execution-safe public benchmark manifest, 12 tasks x 2 trials, hidden verifier enabled, same sanitized disclosure manifest.
- GPT-5.5: Execution-safe public benchmark manifest, 12 tasks x 2 trials, hidden verifier enabled, same sanitized disclosure manifest.; Nexus is measured as a battlesuit worn by the same model, not as a separate agent.

## Final Report Gate

- Final gate: PASS
- Final gate failures: none

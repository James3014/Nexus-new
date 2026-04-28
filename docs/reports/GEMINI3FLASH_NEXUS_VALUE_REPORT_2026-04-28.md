# Gemini 3 Flash + Nexus 價值比對報告

日期：2026-04-28

## What

本次比對同一個模型：

- Baseline：`gemini-3-flash-preview` bare
- Treatment：`gemini-3-flash-preview` wearing Nexus
- 任務集：`scripts/bench/public_benchmark_rlm_harder_v2.json`
- 規模：8 題 x 1 trial
- hidden verifier：開啟
- public claim gate：PASS
- infra invalid：兩邊都是 0

核心結果：

| 指標 | Gemini bare | Gemini + Nexus | 提升 |
| :--- | ---: | ---: | ---: |
| Solve rate | 37.5% | 100.0% | +62.5pp |
| Semantic verified | 37.5% | 100.0% | +62.5pp |
| Trust mismatch | 0.0% | 0.0% | 0.0pp |
| Claim verified | 0.0% | 100.0% | +100.0pp |
| RLM trace present | 0.0% | 100.0% | +100.0pp |
| Token measured rate | 100.0% | 100.0% | 0.0pp |
| Avg wall time | 26.85s | 59.39s | +32.54s |
| Avg model calls | 1.00 | 1.50 | +0.50 |

相對提升：

- Solve rate 從 37.5% 到 100.0%，相對提升約 166.7%。
- Verified delivery 從 37.5% 到 100.0%，相對提升約 166.7%。

## Why

這輪測出的 Nexus 價值不是「更快」，而是「同一個 Gemini 3 Flash 在治理、證據、記憶、信念、驗收約束下，能把結果交付成可驗證成功」。

Nexus 的強項在這輪集中體現在：

1. Artifact / Claim：每個 treatment row 都有 claim verified evidence。
2. MemPalace：治理/邊界類題目 bare 失敗，Nexus 通過。
3. Belief / Memory：Belief/Memory 題型 Nexus 通過，bare 只通過 memory 題、belief 題失敗。
4. RLM trace：Nexus treatment 100% 有 trace，bare 沒有。
5. Hidden verifier：不是看模型自稱成功，而是用隱藏驗證判定。

代價也要一起說：

- Nexus 平均耗時較高：59.39s vs 26.85s。
- Nexus 平均 model calls 較高：1.50 vs 1.00。
- 這代表 Nexus 是高風險任務的強化戰甲，不應對所有低風險任務無差別套重流程。

## How

本次先修了 benchmark framework 的可信度問題，再跑 live benchmark：

- 新增 `--preflight-only`，跑前驗證 model lock、manifest hash、hidden verifier、timeout、evidence bundle，不呼叫 Gemini。
- 修正 bare mode 多階段 timeout：Gemini patch generation 與 pytest 共用同一個 task deadline。
- 修正 benchmark 計時：elapsed/timeout 改用 monotonic time，避免系統時間跳動污染 wall time。
- 先跑 3 題 smoke：Gemini + Nexus 3/3，Gemini bare 0/3，public claim gate PASS。
- 再跑 8 題 x1 expanded run。

證據檔：

- Markdown report：`.nexus/reports/bench_gemini3flash_rlm_v2_8x1_monotonic_20260428_ad59/gemini_nexus_report_1777379811.md`
- Evidence bundle：`.nexus/reports/bench_gemini3flash_rlm_v2_8x1_monotonic_20260428_ad59/evidence_bundle.json`
- With Nexus JSONL：`.nexus/reports/bench_gemini3flash_rlm_v2_8x1_monotonic_20260428_ad59/with_nexus_1777379811.jsonl`
- Without Nexus JSONL：`.nexus/reports/bench_gemini3flash_rlm_v2_8x1_monotonic_20260428_ad59/without_nexus_1777379811.jsonl`

## Per-Task Result

| Task | Capability | Gemini bare | Gemini + Nexus |
| :--- | :--- | :---: | :---: |
| rlm-harder-v2-governance-001 | MemPalace / governance | FAILED | SUCCESS |
| rlm-harder-v2-evidence-001 | Artifact / Claim | FAILED | SUCCESS |
| rlm-harder-v2-governance-002 | MemPalace / governance | FAILED | SUCCESS |
| rlm-harder-v2-evidence-002 | Artifact / Claim | FAILED | SUCCESS |
| rlm-harder-v2-second-round-001 | RLM / second-round repair | SUCCESS | SUCCESS |
| rlm-harder-v2-belief-001 | Belief / Memory | FAILED | SUCCESS |
| rlm-harder-v2-memory-001 | Memory | SUCCESS | SUCCESS |
| rlm-harder-v2-second-round-002 | RLM / second-round repair | SUCCESS | SUCCESS |

## Public Claim Boundary

可說：

- 在這個固定 8 題 hidden-verifier benchmark 上，同一個 Gemini 3 Flash 穿 Nexus 後，verified delivery 從 37.5% 提升到 100.0%。
- Nexus wearing evidence 8/8 有效，Gemini uses Nexus rate 100%，Nexus context delivered rate 100%，claim verified rate 100%。
- 這輪 public claim gate PASS，且 token measured rate 兩邊都是 100%。

不可過度宣稱：

- 這還不是 12 題 x 3 trials 的正式公開最終報告。
- 不可宣稱 Nexus 對所有任務都更快；這輪 Nexus 明顯較慢。
- 不可宣稱 Swarm/Drone/Nightshift 的真實收益，因為本輪這三項沒有觸發。

## Lesson

- Nexus 的產品主指標應是 verified delivery，而不是只看模型回答看起來對不對。
- 高風險任務可以使用 full Nexus；低風險任務應走 light routing，否則 wall time 成本會被放大。
- 公開報告前仍需跑 12x2 或 12x3，以降低單次 trial 偏差。

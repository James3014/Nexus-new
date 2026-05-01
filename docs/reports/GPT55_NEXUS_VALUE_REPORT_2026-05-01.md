# GPT-5.5 + Nexus 價值比對報告

日期：2026-05-01

## What

本報告整理 GPT-5.5 既有 benchmark evidence。主 performance 候選採 `8 題 x 2 trials`，另列 `12 題 x 2 trials` 作 directional observation。

主候選：

- Baseline：`gpt-5.5` bare
- Treatment：`gpt-5.5` wearing Nexus
- 規模：8 題 x 2 trials
- Evidence bundle schema：`nexus_public_benchmark_evidence_bundle_v2`
- Public claim gate：PASS
- Capability-specific / per-capability gate：FAIL
- Infra invalid：兩邊都是 0

核心結果：

| 指標 | GPT-5.5 bare | GPT-5.5 + Nexus | 提升 |
| :--- | ---: | ---: | ---: |
| Eligible rows | 16/16 | 16/16 | - |
| Verified rows | 8/16 | 16/16 | +8 rows |
| Solve rate | 50.0% | 100.0% | +50.0pp |
| Semantic verified | 50.0% | 100.0% | +50.0pp |
| Avg wall time | 9.28s | 65.50s | +56.22s |
| Avg model calls | 1.00 | 1.00 | 0.00 |
| Avg tokens | 12,699.06 | 8,539.56 | -4,159.50 |

## Why

GPT-5.5 本身較強，但在這組 benchmark 上，裸跑仍只達 8/16 verified；穿 Nexus 後達到 16/16。這代表 Nexus 的價值不只對 Gemini 有效，也能在更強模型上提供 verified delivery 增益。

主要價值：

1. Verified delivery：從 50.0% 到 100.0%。
2. Governance / evidence：performance public gate PASS，但 capability-specific gate FAIL，因此不能宣稱單一能力已完整 receipt-backed。
3. 成本型態不同：wall time 顯著增加，但平均 tokens 下降，表示 Nexus 的成本不只看 token，也要看 orchestration time。

## How

主候選證據：

- Report dir：`.nexus/reports/bench_codex55_nexus_capability_8x2_p12`
- With Nexus JSONL：`.nexus/reports/bench_codex55_nexus_capability_8x2_p12/with_nexus_1777455740.jsonl`
- Without Nexus JSONL：`.nexus/reports/bench_codex55_nexus_capability_8x2_p12/without_nexus_1777455740.jsonl`
- Evidence bundle：`.nexus/reports/bench_codex55_nexus_capability_8x2_p12/evidence_bundle.json`
- Markdown report：`.nexus/reports/bench_codex55_nexus_capability_8x2_p12/gemini_nexus_report_1777455740.md`

12x2 directional observation：

| 指標 | GPT-5.5 bare | GPT-5.5 + Nexus | 備註 |
| :--- | ---: | ---: | :--- |
| Rows | 24 | 24 | 12 題 x 2 trials |
| Eligible rows | 23 | 24 | bare 有 1 筆 infra invalid |
| Infra invalid | 1 | 0 | `auth_failed` |
| Eligible verified | 13/23 | 22/24 | observation |
| Eligible solve rate | 56.52% | 91.67% | 觀察性 +35.15pp |
| Avg wall time | 9.88s | 16.45s | Nexus 較慢 |
| Avg model calls | 1.00 | 1.00 | 相同 |
| Avg tokens | 9,111.78 | 11,389.46 | Nexus 較高 |

12x2 directional observation 證據：

- Report dir：`.nexus/reports/bench_codex55_nexus_value_12x2_20260430`
- With Nexus JSONL：`.nexus/reports/bench_codex55_nexus_value_12x2_20260430/with_nexus_1777554172.jsonl`
- Without Nexus JSONL：`.nexus/reports/bench_codex55_nexus_value_12x2_20260430/without_nexus_1777554172.jsonl`
- Evidence bundle：`.nexus/reports/bench_codex55_nexus_value_12x2_20260430/evidence_bundle.json`
- Markdown report：`.nexus/reports/bench_codex55_nexus_value_12x2_20260430/gemini_nexus_report_1777554172.md`

## Public Claim Boundary

可說：

- 在 GPT-5.5 `8 題 x 2 trials` v2 evidence bundle benchmark 上，GPT-5.5 + Nexus 將 verified delivery 從 50.0% 提升到 100.0%，絕對提升 +50.0pp。
- 該主候選 public claim gate PASS，infra invalid 為 0。
- GPT-5.5 + Nexus 的平均 wall time 較高，但主候選平均 tokens 較低。

不可過度宣稱：

- 12x2 observation 不能當 public PASS claim，因 bare 有 1 筆 `auth_failed` infra invalid。
- GPT-5.5 的主候選是 8 題，不是 12 題；不能和 Flash 12 題 headline 直接等量比較。
- 不可宣稱所有任務都更快；8x2 主候選 wall time 從 9.28s 增到 65.50s。
- 不可宣稱單一 capability public-safe outcome contribution；8x2 主候選的 capability-specific / per-capability gate 為 FAIL，原因包含 receipt source missing。

## Lesson

- 對 GPT-5.5，Nexus 的增益仍在 verified delivery，但時間成本更明顯。
- GPT-5.5 最終公開版應補一輪 12 題、0 infra invalid、public/wearing/capability gates 全 PASS 的 v2 run，才能和 Flash 12 題 public PASS 同級。
- 若 12x2 再次出現 auth/infra invalid，應先修 Codex/GPT invocation eligibility，不應把 infra 問題算成模型能力。

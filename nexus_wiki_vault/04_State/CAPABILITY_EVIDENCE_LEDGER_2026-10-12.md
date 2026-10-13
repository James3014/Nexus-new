---
aliases:
- Capability Evidence Ledger
- Citability Ledger 2026-10
confidence: high
last_compiled: '2026-10-12'
owner: agent
related_pages:
- '[Diff - Legacy Monolith vs Split Repo Family (2026-10-12)](../08_Diffs/Diff - Legacy Monolith vs Split Repo Family (2026-10-12).md)'
- '[Ops - Truth Claims Register](../06_Ops/Ops - Truth Claims Register.md)'
- '[NEXUS_FINAL_ACCEPTANCE_MATRIX_2026-05-06](NEXUS_FINAL_ACCEPTANCE_MATRIX_2026-05-06.md)'
source_of_truth: docs/benchmark/benchmark_claim_policy.md; nexus_wiki_vault/10_Analysis_Scans/nexus_am3_post_al_capability_reaudit_20260621.md; nexus-learning repo docs/experiments/2026-10-memory-ab (external)
status: active
tags:
- state
- evidence
- benchmark
- citability
- ledger
title: CAPABILITY_EVIDENCE_LEDGER_2026-10-12
type: report
version_scope:
- v9
- v28
- split-2026-09
---

# Capability Evidence Ledger - 2026-10-12

## One-sentence summary
本頁逐條登記 Wiki 內出現的每個標題數字（benchmark、成功率、token 節省）在 2026-10-12 的可引用性判定，依據是舊 repo 自己的 `benchmark_claim_policy.md`、AM3 再稽核、競爭力現實檢查，以及拆分後 nexus-learning 的記憶 A/B。 [Source: docs/benchmark/benchmark_claim_policy.md] [Source: nexus_wiki_vault/10_Analysis_Scans/nexus_am3_post_al_capability_reaudit_20260621.md]

> [!warning] 使用規則
> 標記 **NOT CITABLE** 的數字不得出現在任何 public claim、investor 材料或新架構的能力宣稱中。標記 **CREDIBLE_UNVERIFIED** 的數字可作內部基線，但引用時必須附帶其限制條件。本頁只判定可引用性，不產生新的 benchmark 結果。

## Role / responsibility
- **可引用性裁定**: 把「wiki 上有這個數字」與「這個數字可以被引用」分開。 [Source: nexus_wiki_vault/06_Ops/Ops - Truth Claims Command Policy.md]
- **兩側對照**: 同一指標若舊單體與拆分後都有量測，並列呈現。 [Source: nexus-learning/docs/experiments/2026-10-memory-ab.md]
- **缺口標記**: 列出舊版有、新版無對應量測的 benchmark，作為 R3 車道復活的目標清單。 [Source: nexus_wiki_vault/08_Diffs/Diff - Legacy Monolith vs Split Repo Family (2026-10-12).md]

## Status legend
- `NOT_CITABLE`: 舊 repo 或後續稽核已證明為模擬、寫死、MagicMock、或無 run ID。
- `PHANTOM_PER_AM3`: 2026-06-21 AM3 再稽核判定對應能力未接線，數字不代表該能力貢獻。
- `CREDIBLE_UNVERIFIED`: 有 run 紀錄與受控對照，但未以 `--strict-llm-baseline` 排除 `model_calls=0` 的確定性 rescue。
- `NEUTRAL`: 量測完成，結果為無顯著差異。
- `UNMEASURED`: 從未有帶能力開關的量測。

## Ledger

| # | Headline number (as written in the vault) | Where it appears | Status | Reason / evidence |
|---|---|---|---|---|
| 1 | Wisdom Layer v22：SWE-bench Pro 77.8% → **87.1%**、GPQA Diamond 97.8%、OSWorld 89.3% | [Ops - Wisdom Layer v22 Architecture](../06_Ops/Ops - Wisdom Layer v22 Architecture.md) | `NOT_CITABLE` | 無 run ID、無 harness 輸出；vault 內真實 SWE-bench 結果為 0/20。 [Source: nexus_wiki_vault/10_Analysis_Scans/nexus-competitive-reality-check.md] |
| 2 | SOTA records：40 tasks / **100%** success (v16) | `nexus_sota_records/README.md` | `NOT_CITABLE` | README 說 40 題、檔案 60 列；v16 orchestrator override；無外部 harness。 |
| 3 | Token A/B 180 runs：Bare 86.7% → Nexus **100%**，token −33%，回歸 8→0 | [NEXUS_EVOLUTION_HISTORY_v9_to_v28](../09_Roadmap/NEXUS_EVOLUTION_HISTORY_v9_to_v28.md) §4.1 | `NOT_CITABLE` | `benchmark_claim_policy.md` §2 點名：180 筆時間戳全在 1 ms 內。 [Source: docs/benchmark/benchmark_claim_policy.md] |
| 4 | Differential Eval 300 tasks；Observation Cycle 01/02/03 | 多頁引用 | `NOT_CITABLE` | 同上：`simulate_task()` 寫死、`MagicMock`、`public_claim_passed` 硬編 True。 |
| 5 | v17.1 → v22.5：成功率 55% → **88%** | `nexus_evidence_pack_20260407/benchmarks.md` | `NOT_CITABLE` | 無 task set、無模型、無 run ID。 |
| 6 | v22 production：100 PR 壓測 P95 2.8 s、Chaos RTO 18 s；v23.1 context −30% | [NEXUS_EVOLUTION_HISTORY_v9_to_v28](../09_Roadmap/NEXUS_EVOLUTION_HISTORY_v9_to_v28.md)、`RELEASE_NOTES.md` | `NOT_CITABLE` | 同頁自述「v1–v25 數字都是雲端模型跑出來的」；−30% 為目標非量測。 |
| 7 | LeanCtx：tokens 1,252 → 114，節省 **90.89%** | [Ops - Performance Benchmarks](../06_Ops/Ops - Performance Benchmarks.md) | `NOT_CITABLE` | 無 task set 與 run 紀錄。 |
| 8 | 9 / 18 Rings 元演化參數；optimization_curve 0.85 → 1.0 | [Meta-Evolution - The 18 Rings Convergence](../04_Research/Meta-Evolution - The 18 Rings Convergence.md) | `NOT_CITABLE` | 參數表無對應 benchmark；兩頁參數值互異（見 C-12）。 |
| 9 | Django #31505：成功率 **100% (Verified)**、2 輪、14,500 tokens | [SOTA Milestone - Django Death Issue Fix](../04_Research/SOTA Milestone - Django Death Issue Fix.md) | `CREDIBLE_UNVERIFIED` (n=1) | 單一案例；頁面自問「不同 DB 後端是否可重現」；Combat Ledger 顯示同批核心任務多為 FAILED。 [Source: nexus_wiki_vault/04_Research/Nexus Combat History Ledger.md] |
| 10 | Skill Memory Closed Loop：Phase 13 acceptance **27/27**、win_rate 收斂 0.6 | [Module - Skill Memory Closed Loop](../02_Modules/Module - Skill Memory Closed Loop.md) | `PHANTOM_PER_AM3` | acceptance 腳本通過，但 AM3 判定 Memory/LanceDB、Learning Closure 在 local_heal 未接線。 |
| 11 | Capability receipts P37：with Nexus solve 100% / semantic verified 100%；CodeIntel、Autoreason、Ultra Review 12/12 | [CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29](../09_Roadmap/CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29.md) | `CREDIBLE_UNVERIFIED` | 12 題、無 Gemini；Swarm / Drone / Nightshift 為 selected-only；頁面自禁 public claim。 |
| 12 | Gemini Flash 12x2（2026-05-05）：Nexus **24/24** vs bare 14/24 (+41.7pp) | [NEXUS_MAY_BENCHMARK_ROUTING_ANALYSIS](../10_Analysis_Scans/NEXUS_MAY_BENCHMARK_ROUTING_ANALYSIS.md) | `CREDIBLE_UNVERIFIED` | 同模型受控對照、有 run；但 ADR 警告部分成功來自 `model_calls=0` 確定性 rescue，需 `--strict-llm-baseline` 重跑。 [Source: nexus_wiki_vault/01_System/ADR/ADR-2026-05-07-teacher-student-sweep-plan.md] |
| 13 | PUBLICATION_READY 12x2（2026-05-20）：24/24 vs 16/24 (+33.3pp) | 同上 | `CREDIBLE_UNVERIFIED` | 同 #12。拆分後**無對應車道量測**（R3）。 |
| 14 | Neutral Fixture 18x3 Pro（2026-04）：54/54 vs 51/54 (+5.56pp) | 同上 | `CREDIBLE_UNVERIFIED` | 同 #12。 |
| 15 | Weak-model route-cost lane P23：Flash+Nexus 12/12 vs bare 7/12；1.01x tokens | [ADR-2026-05-07-teacher-student-sweep-plan](../01_System/ADR/ADR-2026-05-07-teacher-student-sweep-plan.md) | `CREDIBLE_UNVERIFIED` | 同 ADR 註明 deterministic fast-path 不證明模型變強。 |
| 16 | MSA Routing A/B：Unknown Correct Rate 0% → **100%**，cost 0.85 | [MSA_Routing_Architecture](../04_Research/MSA_Routing_Architecture.md) | `CREDIBLE_UNVERIFIED` | 有 A/B 表、無 task set 大小與 run ID。 |
| 17 | Local-heal 8/8 SUCCESS（7B+14B，commit d6d01c3ed） | [NEXUS_MAY_BENCHMARK_ROUTING_ANALYSIS](../10_Analysis_Scans/NEXUS_MAY_BENCHMARK_ROUTING_ANALYSIS.md) | `CREDIBLE_UNVERIFIED` | 8 題自建；同頁其他 astropy "solve" 被 EVOLUTION_HISTORY 自認 overclaim。 |
| 18 | AJ2 / AG5 本地組合：auto solve 57.1% → **65.7%** (23/35) | [nexus_ag1_ag5_local_portfolio_final_report](../10_Analysis_Scans/nexus_ag1_ag5_local_portfolio_final_report.md) | `NOT_CITABLE` | `nexus_asv_final_report.md` 判定 `ASV5_AS_CLAIM_OVERSTATED`、`solve_rate_65_7 UNVERIFIED`、35 題只列 29。 |
| 19 | DeepSWE v26 / full：**0/20** solve_eligible；SWE-bench Lite phase1：1/6 ×3 | `results_deepswe_final_v26.jsonl`、[nexus-competitive-reality-check](../10_Analysis_Scans/nexus-competitive-reality-check.md) | `CITABLE (negative)` | 真實負面結果：REPRO_NOT_REPRODUCED 14/20、模型 20/20 未被呼叫。 |
| 20 | SWE-bench Lite v25.5 overall 0.478；WebArena 0.452 | `results/swe_nexus_v25.5_lite.json` | `NOT_CITABLE` | 無模型、無 harness 輸出、無 instance 清單。 |
| 21 | 記憶 on/off（舊）：memory eval 1 "helped 0 / neutral 4 / distractor 1"；BMF5/6/11 NEUTRAL | `docs/benchmark/nexus_memory_eval_*_final_report.md` (2026-06-21) | `NEUTRAL` | 舊側量測即中性。 |
| 22 | 記憶 on/off（新）：九組設定全 `adoption=DEFER`；最佳輪 off **36/72** vs on **33/72**，sign test p=0.77 | nexus-learning repo `docs/experiments/2026-10-memory-ab.md`；Nexus-new #1785 | `NEUTRAL` | 新側量測亦中性；且 502 份收據均 armor-off（R2），故只證明「裸模型 + 記憶開關」無差異。 |
| 23 | Learning closure：91 episodes / 40 retrieved / **0 applied / 0 uplift**（2026-10-08） | nexus-learning repo `BOUNDARY.md` | `CITABLE (negative)` | 學習閉環未閉合的直接證據。 |
| 24 | Benchmark service / `research:benchmark` | Nexus-new #1762 | `NOT_CITABLE` | `benchmark_service.py` 以亂數產生、幻覺誤報率硬編 0.00%、`research:benchmark` score 常數 1.0。 |
| 25 | Wave 17–46 verifier-feedback rescue（gemini-3.1-pro）：one-shot 0/3 vs adaptive 1/3；Wave 40 baseline 2/15 → +insight 9/15 | Nexus-new #1503, #1588, #1595, #1606 | `CREDIBLE_UNVERIFIED` (n≤15) | 小樣本、單一受試者（WFV1-S2-05）；Wave 45 holdout 0/2。 |
| 26 | R3 Hybrid Economics：Online 16/24 vs deterministic-first 23/24；online calls −33.3% | Nexus-new #1185 | `CREDIBLE_UNVERIFIED` | Owner-reported；closure evidence `PENDING_DURABLE_RESULT_IDENTITY`。 |
| 27 | DDTree / Belief / Hyper / Autoreason / Learning Closure 個別能力貢獻 | 全 vault | `UNMEASURED` | AM3 消融結果全為 NO-OP（未接線）；拆分後唯一有開關的量測只有記憶（#22）。 |

## Legacy benchmarks with no post-split counterpart
- Gemini 同模型 Nexus-vs-bare 車道（#12–#14、P90 三臂）。
- Teacher/student gap matrix（GPT-5.5+Nexus vs Flash+Nexus）。
- DeepSWE / SWE-bench Lite 任何形式的 run。
- 能力逐一消融（#27）。

## Upstream
- **[Ops - Truth Claims Register](../06_Ops/Ops - Truth Claims Register.md)**: 可被命令驗證的 claim 清單；本頁補其無法命令驗證的數字部分。
- **[NEXUS_FINAL_ACCEPTANCE_MATRIX_2026-05-06](NEXUS_FINAL_ACCEPTANCE_MATRIX_2026-05-06.md)**: `BENCHMARK_DEBT` 狀態的原始定義。

## Downstream
- **[Diff - Legacy Monolith vs Split Repo Family (2026-10-12)](../08_Diffs/Diff - Legacy Monolith vs Split Repo Family (2026-10-12).md)**: 能力對位表的「Evidence status」欄取自本頁。
- **[Investor Deck](../00_Product/Investor Deck.md)**、**[Go-to-Market](../05_Commercial/Go-to-Market.md)**: 對外材料引用數字前須先查本頁。

## Related modules / files
- `docs/benchmark/benchmark_claim_policy.md`: 舊 repo 自行列出的不可引用資料。 [Source: docs/benchmark/benchmark_claim_policy.md]
- `scripts/bench/with_nexus_runner.py`, `scripts/bench/capability_ab_runner.py`: #12–#14 的 runner。 [Code: scripts/bench/capability_ab_runner.py]
- `scripts/eval/run_memory_ab_v1.py`: #22 的 runner。 [Code: scripts/eval/run_memory_ab_v1.py]

## Source notes
- 舊側數字取自 vault 頁面與 `nexus/` legacy clone 下的 results / docs/benchmark；新側取自 nexus-learning docs 與 Nexus-new issues（2026-10-12 以 `gh` 讀取）。 [Source: nexus_wiki_vault/09_Roadmap/NEXUS_EVOLUTION_HISTORY_v9_to_v28.md]
- 判定不做新量測；R2/R3 修復後應以新 run 覆寫 #12–#14、#22 的狀態。

## Open questions / conflicts
- [ ] #12–#14 以 `--strict-llm-baseline` 重跑後若 uplift 消失，是否將整個 Gemini 車道降為 `NOT_CITABLE`？
- [ ] #9 Django 案例是否值得補第二個 DB 後端的重現以升級為 `CITABLE`？
- [ ] 本頁是否應由 `wiki_truth_claims_check.py` 自動比對 `.nexus/reports/` 下的新 run？

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]

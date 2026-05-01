# Gemini 3.1 Pro + Nexus 價值比對報告

Report date：2026-05-01

Evidence date：2026-04-28

## What

本報告整理既有 historical benchmark evidence，不是 2026-05-01 新跑的 hardened rerun。

- Baseline：`gemini-3.1-pro-preview` bare
- Treatment：`gemini-3.1-pro-preview` wearing Nexus
- 任務集：`scripts/bench/public_benchmark_nexus_value_v1.json`
- 規模：12 題 x 2 trials
- Hidden verifier：開啟
- Infra invalid：兩邊都是 0
- Evidence bundle schema：`nexus_public_benchmark_evidence_bundle_v1`
- Public claim gate：markdown report 顯示 PASS；bundle v1 本身沒有 self-describing `public_claim_gate` object

核心結果：

| 指標 | Gemini 3.1 Pro bare | Gemini 3.1 Pro + Nexus | 提升 |
| :--- | ---: | ---: | ---: |
| Eligible rows | 24/24 | 24/24 | - |
| Verified rows | 5/24 | 24/24 | +19 rows |
| Solve rate | 20.83% | 100.00% | +79.17pp |
| Semantic verified | 20.83% | 100.00% | +79.17pp |
| Trust mismatch | 0.00% | 0.00% | 0.00pp |
| Avg wall time | 17.98s | 48.49s | +30.51s |
| Avg model calls | 1.00 | 1.79 | +0.79 |
| Avg tokens | 21,161.88 | 39,662.71 | +18,500.83 |

## Why

這份 historical evidence 顯示：同一個 Gemini 3.1 Pro 在裸跑時，對需要治理、上下文、失敗修復與證據驗收的任務容易未達 hidden verifier；穿 Nexus 後，verified delivery 達到 24/24。

Nexus 的主要補位：

1. `test_repair`：自癒、Hyper、Artifact 驗收。
2. `refactor/governance`：MemPalace 治理邊界、Belief 決策、Claim 驗證。
3. `feature/evidence`：Artifact / Claim causality。
4. `docs_code_sync/context`：LanceDB / Memory / context delivery。
5. `ops_research/trust`：research / hyper / trust alignment。

代價也明確：

- Nexus 平均 wall time 增加約 30.51s。
- 平均 model calls 從 1.00 增到 1.79。
- 平均 tokens 從 21,161.88 增到 39,662.71。

## How

證據來源：

- 中文歷史報告：`docs/reports/NEXUS_GEMINI31PRO_VALUE_BENCHMARK_2026-04-28.md`
- Raw with Nexus：`.nexus/reports/bench_gemini31pro_value12x2_caffeinated_20260428/with_nexus_1777325568.jsonl`
- Raw bare：`.nexus/reports/bench_gemini31pro_value12x2_caffeinated_20260428/without_nexus_1777325568.jsonl`
- Evidence bundle：`.nexus/reports/bench_gemini31pro_value12x2_caffeinated_20260428/evidence_bundle.json`
- Markdown report：`.nexus/reports/bench_gemini31pro_value12x2_caffeinated_20260428/gemini_nexus_report_1777325568.md`

## Public Claim Boundary

可說：

- 在 2026-04-28 historical 12 題 x 2 trials hidden-verifier benchmark 上，同一個 `gemini-3.1-pro-preview` 穿 Nexus 後，verified delivery 從 20.83% 提升到 100.00%，絕對提升 +79.17pp。
- 該輪 infra invalid 為 0，trust mismatch 為 0.00%。
- 該輪 treatment rows 24/24 皆有 Nexus wearing evidence、五支柱與六階段 evidence。
- Token telemetry 24/24 measured，來源是 gateway `stats`，不是 usage metadata。

不可過度宣稱：

- 這不是 2026-05-01 hardened evidence bundle v2 rerun。
- 舊 evidence bundle 是 `v1`，不含新版 v2 的 `run_identity`、`model_lock`、`task_manifest`、`timeouts`、`row_counts`、`telemetry_completeness`、`nexus_wearing`、`public_claim_gate`；不能和 Flash 2026-05-01 v2 public PASS 報告視為完全同級。
- 2026-05-01 重新跑 `gemini-3.1-pro-preview` 時，Codex 執行審核器拒絕將本機 benchmark prompt/task data 傳給外部 Gemini 3.1 Pro；因此本報告暫採 historical evidence。
- 不可宣稱 Nexus 對 Pro 更快；本輪 Nexus 明顯更慢且更耗 token。

## Lesson

- Pro 舊數據很強，但要進最終公開報告，需要標明 evidence generation date 與 schema version。
- 若要新版 hardened rerun，應先做 sanitized/public benchmark prompt，避免 external disclosure policy 阻擋。
- Pro 的公開話術應是 historical candidate evidence，不是 2026-05-01 hardened rerun evidence。

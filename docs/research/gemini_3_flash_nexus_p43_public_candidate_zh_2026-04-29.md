# Gemini 3 Flash + Nexus 公開候選比對報告（P43）

日期：2026-04-29  
狀態：公開候選，可作內部/半公開說明；正式產品宣稱前建議再跑 12x2 或 12x3。

## What

本次測試比較同一個模型在兩種狀態下的表現：

- Baseline：`gemini-3-flash-preview_bare`
- Treatment：`gemini-3-flash-preview_nexus`
- 題目：`scripts/bench/public_benchmark_nexus_value_v1.json`
- 範圍：12 題 x 1 trial
- 驗證：hidden verifier + evidence bundle + public claim gate

原始證據：

- Without Nexus：`.nexus/reports/bench_gemini3flash_p43_12x1_20260428/without_nexus_1777390762.jsonl`
- With Nexus：`.nexus/reports/bench_gemini3flash_p43_12x1_20260428/with_nexus_1777390762.jsonl`
- Evidence bundle：`.nexus/reports/bench_gemini3flash_p43_12x1_20260428/evidence_bundle.json`
- Markdown report：`.nexus/reports/bench_gemini3flash_p43_12x1_20260428/gemini_nexus_report_1777390762.md`

## Why

這份 benchmark 不只看答案是否「看起來對」，而是看 Nexus 是否能把 Gemini 的輸出變成「可驗證、可追蹤、可交付」。

Nexus 的產品價值在這次測試中主要體現在：

- Verified delivery：結果必須通過 hidden verifier 與 evidence gate。
- Nexus wearing：Gemini 必須真的經過 Nexus context/gate/phase，而不是 Nexus 代解。
- Anti-hallucination：claim 需要有 artifact/evidence 支撐。
- Governance：MemPalace、Belief、Artifact/Claim 等支柱要在 row evidence 中留下訊號。

## How

執行方式採 sequential A/B，同一題先後測 bare 與 Nexus，並啟用：

- same model lock：兩組都是 `gemini-3-flash-preview`
- hidden verifier：啟用
- history neutralization：每題重置，避免學習污染
- learning loop：關閉，避免 benchmark 期間累積記憶造成不公平
- evidence bundle：啟用
- public claim gate：啟用

本次 evidence bundle 顯示：

- Same model：PASS
- Public claim gate：PASS
- Gemini uses Nexus rate：100.0%
- Nexus context delivered rate：100.0%
- Nexus usage valid rate：100.0%
- Claim verified rate：100.0%

## 結果

| 指標 | Gemini 3 Flash bare | Gemini 3 Flash + Nexus | 提升 |
| --- | ---: | ---: | ---: |
| Usable rows | 10/12 | 12/12 | Nexus 少 2 筆 infra invalid |
| Infra invalid rows | 2 | 0 | +2 rows usable |
| Eligible solve rate | 30.0% | 100.0% | +70.0pp |
| Semantic verified | 25.0% | 100.0% | +75.0pp |
| Trust mismatch | 0.0% | 0.0% | 持平 |
| Avg wall time | 46.55s | 83.69s | +37.14s |
| Avg model calls | 0.92 | 1.58 | +0.66 |
| Token measured rate | 83.3% | 100.0% | +16.7pp |
| LLM self-heal rate | 0.0% | 58.3% | +58.3pp |

可公開候選說法：

> 在這組固定 12 題公開候選 benchmark 中，`gemini-3-flash-preview` 穿上 Nexus 後，eligible solve rate 從 30.0% 提升到 100.0%，絕對提升 70.0 個百分點，且 trust mismatch 維持 0.0%。同時 Nexus 產生了 100.0% 的 wearing/context/evidence 訊號，表示 Gemini 確實是在 Nexus 管線中完成工作。

## Nexus 強在哪

這次勝出的任務集中在 bare Gemini 容易失敗或無法穩定驗證的區域：

- Repair / self-heal：`nexus-value-repair-001`, `nexus-value-repair-002`
- Governance：`nexus-value-gov-001`, `nexus-value-gov-002`
- Artifact / Claim：`nexus-value-evidence-001`, `nexus-value-evidence-002`, `nexus-value-trust-002`
- Context / Memory / Belief：`nexus-value-context-001`, `nexus-value-context-002`

這說明 Nexus 的主要價值不是讓模型「更會聊天」，而是讓同一個模型在交付型任務上具備：

- 更穩的驗證閉環
- 更清楚的 evidence trail
- 更低的不可採信輸出風險
- 更高的任務完成可交付率

## 成本與限制

Nexus 不是免費提升。這次數據顯示：

- 平均 wall time 增加 37.14 秒。
- 平均 model calls 增加 0.66。
- 12x1 仍是小樣本，正式產品宣稱前建議跑 12x2 或 12x3。
- 本次 runner command 未啟用 `NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin` 與 `NEXUS_GATEWAY_COMPACT_PROMPT=1`，正式發布前應用完整推薦 env 重跑。
- Autoreason/DDTree/Ultra Review 在本次 P43 不是主要生效來源；後續需要用專門題組與 row evidence 補強。

## P44-P46 結論

- P44：12x1 已足以作公開候選，不建議立刻再燒一次 12x2；正式發布前安排夜間 12x2/12x3。
- P45：本中文報告作為可讀版本，原始 JSONL/evidence bundle 作為可審計版本。
- P46：下一輪優化應優先降低 Nexus wall time，同時讓 Autoreason、DDTree、Ultra Review 的 row evidence 真正出現在 benchmark 指標中。

## 下一輪正式發布前置

1. 用完整 env 重跑：
   - `NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin`
   - `NEXUS_GATEWAY_COMPACT_PROMPT=1`
   - `NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=420`
   - `NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=240`
2. 跑 12x2 或 12x3，確認提升不是單次樣本偶然。
3. 增加 capability-specific 題組，分別量化 CodeIntel、JIT、RLM、Autoreason、DDTree、Ultra Review。
4. 將報告主指標固定為 `verified delivery / eligible solve rate / trust mismatch / wall time / model calls / token measured rate`。

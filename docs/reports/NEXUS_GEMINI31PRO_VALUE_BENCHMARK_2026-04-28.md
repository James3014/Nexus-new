# Nexus Value Benchmark Report - Gemini 3.1 Pro Preview

日期：2026-04-28

## 結論

在固定 12 題、每題 2 次的 hidden-verifier benchmark 中，同一個模型 `gemini-3.1-pro-preview`：

| 指標 | Gemini bare | Gemini + Nexus | 提升 |
| --- | ---: | ---: | ---: |
| 可用樣本 | 24/24 | 24/24 | - |
| Infra invalid | 0 | 0 | - |
| Solve rate | 20.83% | 100.00% | +79.17 pp |
| Semantic verified | 20.83% | 100.00% | +79.17 pp |
| Trust mismatch | 0.00% | 0.00% | 0.00 pp |
| 平均 wall time | 17.98s | 48.49s | +30.52s |
| 平均 model calls | 1.00 | 1.79 | +0.79 |
| 平均 tokens | 21,161.88 | 39,662.71 | +18,500.83 |

這代表 Nexus 的主要價值不是「少呼叫模型」或「更快」，而是讓同一個 Gemini 在需要治理、驗證、上下文與自癒的任務中更穩定交付。這次代價是平均 wall time 約增加 30.52s，平均模型呼叫從 1.00 增加到 1.79。

## Nexus 強在哪

| 題型 | Gemini bare | Gemini + Nexus | 對應 Nexus 能力 |
| --- | ---: | ---: | --- |
| bugfix | 3/4 | 4/4 | hidden verifier 下仍能維持修補能力 |
| test_repair | 0/4 | 4/4 | 自癒、Artifact 驗收、失敗測試修復 |
| refactor/governance | 0/4 | 4/4 | MemPalace 治理邊界、Belief 決策、Claim 驗證 |
| feature/evidence | 0/4 | 4/4 | Artifact 證據、Claim verified |
| docs_code_sync/context | 0/4 | 4/4 | LanceDB/RAG context delivery |
| ops_research/trust | 2/4 | 4/4 | research/hyper 流程與 trust alignment |

## 戰甲穿戴證據

Nexus 是戰甲，不是獨立 agent。這次 treatment rows 皆確認 Gemini 有穿 Nexus：

| 證據 | 結果 |
| --- | ---: |
| `gemini_uses_nexus` + `nexus_context_delivered` + `nexus_wearing_valid` | 24/24 |
| 五支柱 observed: LanceDB, Memory, MemPalace, Belief, Artifact | 24/24 |
| 六階段 observed: P, X, D, R, A, C | 24/24 |
| `capability_claim_verified` | 24/24 |
| research used | 24/24 |
| hyper used | 24/24 |
| LLM self-heal used | 16/24 |
| swarm used | 16/24 |
| drone used | 0/24 |
| nightshift recommended | 0/24 |

## 可公開宣稱版本

可公開候選宣稱：

> 在固定 12 題 x 2 trials 的 hidden-verifier benchmark 上，使用同一個 `gemini-3.1-pro-preview`，Gemini + Nexus 將 verified delivery 從 20.83% 提升到 100.00%，絕對提升 +79.17 個百分點；trust mismatch 維持 0.00%。Nexus treatment 24/24 rows 皆有穿戴證據與五支柱/六階段 evidence。

建議公開時同步揭露成本：

> 這個提升不是免費的：Gemini + Nexus 平均 wall time 從 17.98s 增加到 48.49s，平均 model calls 從 1.00 增加到 1.79，平均 tokens 從 21,161.88 增加到 39,662.71。Nexus 的定位是提升 verified delivery，不是節省推論成本。

## 不能過度宣稱

- 這不是 Gemini 3 Flash 數據；本輪模型是 `gemini-3.1-pro-preview`。
- 這不是廣義所有任務的生產結論；它是 frozen benchmark 上的 public-candidate evidence。
- `drone` 與 `nightshift` 本輪沒有觸發，不能用這份數據宣稱它們帶來提升。
- Nexus 更慢且更耗 token；公開時必須同時說明成功率提升與成本增加。

## Evidence

- Raw with Nexus: `.nexus/reports/bench_gemini31pro_value12x2_caffeinated_20260428/with_nexus_1777325568.jsonl`
- Raw bare: `.nexus/reports/bench_gemini31pro_value12x2_caffeinated_20260428/without_nexus_1777325568.jsonl`
- Evidence bundle: `.nexus/reports/bench_gemini31pro_value12x2_caffeinated_20260428/evidence_bundle.json`
- Markdown report: `.nexus/reports/bench_gemini31pro_value12x2_caffeinated_20260428/gemini_nexus_report_1777325568.md`
- Runner hardening commit: `ffe35fd3 fix: harden capability benchmark stop loss`

## Lessons

- 失敗教訓：長 benchmark 若沒有防睡眠，macOS/執行環境暫停會讓 wall-clock row 跳到 1000s，污染公開數據。
- 修正：正式長跑改用 `caffeinate -dimsu`；runner 新增 `--per-task-stop-loss-sec 600`，超過門檻會標 `task_stop_loss_exceeded` 並停止。
- 報告教訓：partial run 不能讓 markdown renderer crash；現在會產出 Public claim gate FAIL 的 partial report。
- 標題教訓：報告標題不可硬編 Gemini 3 Flash；已改成依 treatment label 產生。

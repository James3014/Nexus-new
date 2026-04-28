# Nexus Value Benchmark Report - Gemini 3 Flash Preview

日期：2026-04-28

## 結論

在固定 12 題、每題 2 次的 hidden-verifier benchmark 中，同一個模型 `gemini-3-flash-preview`：

| 指標 | Gemini bare | Gemini + Nexus | 提升 |
| --- | ---: | ---: | ---: |
| 可用樣本 | 24/24 | 24/24 | - |
| Infra invalid | 0 | 0 | - |
| Solve rate | 37.50% | 100.00% | +62.50 pp |
| Semantic verified | 37.50% | 100.00% | +62.50 pp |
| Trust mismatch | 0.00% | 0.00% | 0.00 pp |
| 平均 wall time | 48.93s | 72.30s | +23.36s |
| 平均 model calls | 1.00 | 1.67 | +0.67 |
| 平均 tokens | 24,265.00 | 46,564.21 | +22,299.21 |

這份結果顯示 Nexus 對 Gemini 3 Flash 的價值是提升 verified delivery，而不是節省時間或 token。

## Nexus 強在哪

| 題型 | Gemini bare | Gemini + Nexus | 對應 Nexus 能力 |
| --- | ---: | ---: | --- |
| bugfix | 4/4 | 4/4 | Flash bare 已能處理，Nexus 無明顯 solve-rate 優勢 |
| test_repair | 0/4 | 4/4 | 自癒、Artifact 驗收、失敗測試修復 |
| refactor/governance | 3/4 | 4/4 | MemPalace/Belief 治理讓結果更穩 |
| feature/evidence | 0/4 | 4/4 | Artifact 證據、Claim verified |
| docs_code_sync/context | 1/4 | 4/4 | LanceDB/RAG context delivery |
| ops_research/trust | 1/4 | 4/4 | research/hyper 流程與 trust alignment |

## 戰甲穿戴證據

| 證據 | 結果 |
| --- | ---: |
| `gemini_uses_nexus` + `nexus_context_delivered` + `nexus_wearing_valid` | 24/24 |
| 五支柱 observed: LanceDB, Memory, MemPalace, Belief, Artifact | 24/24 |
| 六階段 observed: P, X, D, R, A, C | 24/24 |
| `capability_claim_verified` | 24/24 |
| research used | 24/24 |
| hyper used | 24/24 |
| LLM self-heal used | 14/24 |
| swarm used | 16/24 |
| drone used | 0/24 |
| nightshift recommended | 0/24 |

## 可公開宣稱版本

> 在固定 12 題 x 2 trials 的 hidden-verifier benchmark 上，使用同一個 `gemini-3-flash-preview`，Gemini + Nexus 將 verified delivery 從 37.50% 提升到 100.00%，絕對提升 +62.50 個百分點；trust mismatch 維持 0.00%。Nexus treatment 24/24 rows 皆有穿戴證據與五支柱/六階段 evidence。

同步揭露成本：

> Gemini + Nexus 平均 wall time 從 48.93s 增加到 72.30s，平均 model calls 從 1.00 增加到 1.67，平均 tokens 從 24,265.00 增加到 46,564.21。Nexus 的定位是提高可驗證交付率，不是降低推論成本。

## Evidence

- Raw with Nexus: `.nexus/reports/bench_gemini3flash_value12x2_caffeinated_20260428/with_nexus_1777331426.jsonl`
- Raw bare: `.nexus/reports/bench_gemini3flash_value12x2_caffeinated_20260428/without_nexus_1777331426.jsonl`
- Evidence bundle: `.nexus/reports/bench_gemini3flash_value12x2_caffeinated_20260428/evidence_bundle.json`
- Markdown report: `.nexus/reports/bench_gemini3flash_value12x2_caffeinated_20260428/gemini_nexus_report_1777331426.md`

## Lessons

- Flash bare 在 bugfix 類題型已很強，不能用「裸模型很弱」作為產品敘事。
- Nexus 的明確勝點集中在 test_repair、evidence、context、trust 題型。
- context-001 bare 一次耗時 420.12s 後仍失敗，顯示長 context 任務需要更好的 stop/budget/trace 內迴圈。

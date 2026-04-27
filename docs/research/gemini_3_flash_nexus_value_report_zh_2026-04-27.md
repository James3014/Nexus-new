# Gemini 3 Flash 穿 Nexus：價值證據報告

日期：2026-04-27

狀態：公開候選證據 v1。這份報告使用 hidden verifier，且已通過 public claim gate；它可以作為 Nexus 價值說明的核心資料，但仍建議用 12x2/12x3 重跑做 publication-grade 穩定性確認。

## 一句話結論

在同一組 12 題 hidden-verifier benchmark 上，`gemini-3-flash-preview` bare 完成 3/12 = 25.0%，`gemini-3-flash-preview` 穿 Nexus 完成 12/12 = 100.0%，提升 75.0 percentage points。

Nexus 的價值不是「換模型」，而是讓同一個 Gemini 3 Flash 進入可治理、可驗證、可自癒的工程迴圈。

## 主證據

原始資料：

- `.nexus/reports/bench_gemini3flash_value12x1_hidden_timeoutfix_full12/without_nexus_1777293163.jsonl`
- `.nexus/reports/bench_gemini3flash_value12x1_hidden_timeoutfix_full12/with_nexus_1777293163.jsonl`
- `.nexus/reports/bench_gemini3flash_value12x1_hidden_timeoutfix_full12/evidence_bundle.json`
- `.nexus/reports/bench_gemini3flash_value12x1_hidden_timeoutfix_full12/gemini_nexus_report_1777293163.md`

設定：

- Model：`gemini-3-flash-preview`
- Baseline：Gemini 3 Flash bare
- Treatment：Gemini 3 Flash + Nexus
- `hidden_verifier_mode=true`
- `repeat_trials=1`
- `max_tasks=12`
- `public claim gate=PASS`
- 未混用 `gemini-3.1-pro-preview`

## 整體結果

| 指標 | Gemini 3 Flash bare | Gemini 3 Flash + Nexus | 提升 |
| --- | ---: | ---: | ---: |
| usable rows | 12/12 | 12/12 | n/a |
| infra invalid rows | 0 | 0 | n/a |
| solve rate | 25.0% | 100.0% | +75.0 pp |
| semantic verified | 25.0% | 100.0% | +75.0 pp |
| trust mismatch | 0.0% | 0.0% | 0.0 pp |
| public claim gate | n/a | PASS | PASS |
| avg wall time | 42.82s | 54.99s | Nexus 慢 28.4% |
| avg model calls | 1.00 | 1.67 | +0.67 |
| token measured rate | 91.7% | 100.0% | +8.3 pp |
| LLM self-heal rate | 0.0% | 66.7% | +66.7 pp |
| Nexus wearing evidence | 0/12 | 12/12 | +100.0 pp |
| phase completion | 0/12 | 12/12 | +100.0 pp |
| claim verified | 0/12 | 12/12 | +100.0 pp |

## 題目明細

| 題目 | bare | Nexus | Nexus 主要差異 |
| --- | --- | --- | --- |
| hidden-001 | PASS | PASS | 雙方皆可解 |
| hidden-002 | PASS | PASS | 雙方皆可解 |
| repair-001 | FAIL | PASS | Nexus self-heal 成功 |
| repair-002 | FAIL | PASS | Nexus self-heal 成功 |
| gov-001 | PASS | PASS | 雙方皆可解 |
| gov-002 | FAIL | PASS | Nexus self-heal 成功；timeout budget 修正後穩定 |
| evidence-001 | FAIL | PASS | Nexus artifact/self-heal 成功 |
| evidence-002 | FAIL | PASS | Nexus artifact/self-heal 成功 |
| context-001 | FAIL | PASS | bare timeout，Nexus self-heal 成功 |
| context-002 | FAIL | PASS | Nexus context/self-heal 成功 |
| trust-001 | FAIL | PASS | Nexus governance closure 成功 |
| trust-002 | FAIL | PASS | Nexus self-heal 成功 |

## Nexus 到底提升了什麼

1. **解題率提升。** 同模型同題庫，bare 25.0%，Nexus 100.0%，+75.0 pp。
2. **自癒能力提升。** Nexus 有 8/12 rows 觸發 LLM self-heal；bare 沒有第二階段修復能力。
3. **抗幻覺維持。** 兩邊 trust mismatch 都是 0.0%，Nexus 沒用不可信答案換成功率。
4. **治理證據完整。** Nexus 12/12 都有穿戴證據、六階段、claim verified；bare 沒有可審計 closure。
5. **隱藏驗證更接近真實工程。** visible tests 不再直接餵給 bare，能測出「一次性 patch」和「工程迴圈」的差距。

## 代價

Nexus 不是免費提升：

- 平均 wall time 從 42.82s 增加到 54.99s，慢 28.4%。
- 平均 model calls 從 1.00 增加到 1.67。
- 這些成本主要來自 self-heal 與 artifact verification。

合理說法是：Nexus 用更多工程流程與少量額外模型呼叫，換到顯著更高的 hidden-verifier 成功率與完整治理證據。

## 修正過程的重要教訓

前一輪 12x2 easy-mode 得到 bare 100%、Nexus 100%，原因是沒有啟用 `NEXUS_VALUE_HIDDEN_VERIFIER=1`，題目對 bare 太容易。該資料只能當 regression，不可當能力價值證據。

另一個缺口是 Nexus gateway timeout 原本固定 30s，導致 `gov-002` 的 Gemini 呼叫在 Nexus 內被過早殺掉。修正為依 task timeout 放大後，`gov-002` 從 Nexus FAIL 轉為 PASS，完整 12 題 public claim gate 也轉為 PASS。

## 可對外說法

可說：

> 在一組 12 題 hidden-verifier 工程任務上，Gemini 3 Flash bare 的 semantic verified rate 是 25.0%，Gemini 3 Flash + Nexus 是 100.0%，提升 75.0 percentage points，且 trust mismatch 維持 0.0%。Nexus 的提升主要來自 self-heal、artifact verification、治理 closure 與六階段 evidence trail。

必須一起說：

> 這是 12 題 x 1 trial 的公開候選資料；正式 publication-grade 主張前，仍應以相同 protocol 重跑 12x2 或 12x3，並保留原始 JSONL/evidence bundle。

不可說：

> Nexus 永遠讓 Gemini 3 Flash 提升 75 percentage points。

不可說：

> Nexus 比 bare 更快或更省模型呼叫。

## 下一步

P1. 將 `nexus ask` strict-topic drift 修補同步到主工作區 `/Users/jameschen/Workspace/nexus`，避免分支/工作樹不一致。

P2. 將這輪 timeout/gate 修正與報告整理成一個乾淨 commit。

P3. 用相同設定跑 12x2 hidden verifier：

- 目標：Nexus 仍維持 100% 或至少明顯高於 bare。
- public claim gate 必須 PASS。
- 若 Gemini 3 Flash 額度不足，改用 `gemini-3.1-pro-preview` 另開報告，不可混入 Flash 結論。

P4. 建立固定「Nexus value benchmark skill」：

- 每次優化前後都跑同題庫。
- 自動輸出 solve rate、semantic verified、trust mismatch、wall time、tokens、model calls、self-heal rate、public gate。

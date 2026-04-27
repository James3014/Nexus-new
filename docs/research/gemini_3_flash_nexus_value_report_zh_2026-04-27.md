# Gemini 3 Flash 穿 Nexus：價值對比報告

日期：2026-04-27

狀態：公開說明候選稿 v0.2。這版比 v0.1 多了 6x2 重跑與全 12 題 coverage sweep，因此結論分成「已看見明確價值」與「尚未能泛化」兩層。

## 一句話結論

在 hidden-verifier 的 governance / evidence / trust 六題、每題 2 trials 上，Gemini 3 Flash 穿 Nexus 後，semantic verified rate 從 33.3% 提升到 58.3%，提升 25.0 percentage points。

最明確的價值集中在 trust/self-heal 題型：trust 題裸 Gemini 是 1/4，Gemini+Nexus 是 4/4，提升 75.0 percentage points。

但全 12 題 coverage sweep 不支持「Nexus 全面勝過 bare Gemini」這種說法：全 12x1 裸 Gemini 是 50.0%，Gemini+Nexus 是 33.3%。所以目前可以公開說的是：Nexus 在 hidden-verifier 的 trust/self-heal 題型上有明確提升；其他題型仍需要下一輪能力調整。

## 實驗設定

| 項目 | 設定 |
| --- | --- |
| 模型 | `gemini-3-flash-preview` |
| 對照組 | Gemini 3 Flash bare |
| 實驗組 | Gemini 3 Flash + Nexus |
| 題庫 | `scripts/bench/public_benchmark_nexus_value_v1.json` |
| 主結論樣本 | governance / evidence / trust 六題 x 2 trials |
| 泛化檢查 | 全 12 題 x 1 trial |
| 模式 | `NEXUS_VALUE_HIDDEN_VERIFIER=1` |
| Nexus gateway timeout | 45s |
| per-task timeout | 120s |
| manifest SHA-256 | `432973357dd93c597b7ae95c65e391207d4607f1f6af130cdfdbc261a19894ad` |

Hidden-verifier 的意思是：初始 prompt 不直接提供 verifier tests。裸 Gemini 只能一次產生 patch；Nexus 可以在執行驗收後，用失敗證據進行 bounded repair/self-heal。這對應 Nexus 作為「戰甲」的核心能力，而不是單純比誰看見測試後能改檔。

## 主結論數據：GET 6x2

GET 代表 governance / evidence / trust。這組是目前最適合公開說明 Nexus 價值的固定小樣本，因為它直接測治理、證據、信任與自癒閉環。

| 指標 | Gemini bare | Gemini+Nexus | 差異 |
| --- | ---: | ---: | ---: |
| semantic verified | 4/12 = 33.3% | 7/12 = 58.3% | +25.0 pp |
| trust mismatch | 0.0% | 0.0% | 持平 |
| 平均 wall time | 36.32s | 45.29s | +8.97s |
| 平均 tokens | 31,275 | 32,730 | +1,456 |
| 平均 model calls | 1.00 | 1.42 | +0.42 |
| LLM self-heal rate | 0.0% | 41.7% | +41.7 pp |
| token measured rate | 100.0% | 91.7% | -8.3 pp |
| infra invalid | 0 | 0 | 持平 |

## 能力分解

| 題型 | Gemini bare | Gemini+Nexus | 差異 | 解讀 |
| --- | ---: | ---: | ---: | --- |
| governance | 3/4 = 75.0% | 3/4 = 75.0% | 0.0 pp | Nexus 沒有明顯提升，但也清掉 v0.1 的 delivery invalid |
| evidence | 0/4 = 0.0% | 0/4 = 0.0% | 0.0 pp | 目前兩邊都弱，是下一波能力缺口 |
| trust | 1/4 = 25.0% | 4/4 = 100.0% | +75.0 pp | Nexus 最明確的價值區 |

## Row-level 結果：GET 6x2

| 題目 | bare | Nexus | Nexus winner / 備註 |
| --- | ---: | ---: | --- |
| `nexus-value-gov-001` | 2/2 | 2/2 | `llm` |
| `nexus-value-gov-002` | 1/2 | 1/2 | 其中 1 次靠 `llm_self_heal` |
| `nexus-value-evidence-001` | 0/2 | 0/2 | 持平失敗 |
| `nexus-value-evidence-002` | 0/2 | 0/2 | 持平失敗 |
| `nexus-value-trust-001` | 1/2 | 2/2 | 2 次都靠 `llm_self_heal` |
| `nexus-value-trust-002` | 0/2 | 2/2 | 2 次都靠 `llm_self_heal` |

## Nexus 到底提升了什麼

### 1. 自癒成功率

主樣本中 Nexus 有 5/12 rows 使用 `llm_self_heal`，其中包含 trust 題 4/4 全過。這說明 Gemini 穿 Nexus 後，不只是一次回答，而是能用驗收失敗證據再修一次。

這是目前最清楚的產品價值：把「一次沒答對」變成「可驗收、可修復、可留下證據」。

### 2. Trust 題型

trust 題裸 Gemini 是 25.0%，Gemini+Nexus 是 100.0%。這是本輪最強的能力差異。

可公開說法：

> 在 hidden-verifier trust 題型上，Gemini 3 Flash + Nexus 將 semantic verified rate 從 25.0% 提升到 100.0%。提升來自 Nexus 的驗收失敗回饋與 bounded self-heal。

### 3. 治理與證據鏈

裸 Gemini rows 沒有 Nexus 五支柱與六階段 evidence。Nexus rows 會留下：

- Gemini 是否真的穿 Nexus：`gemini_uses_nexus`
- Nexus context 是否送達：`nexus_context_delivered`
- 五支柱觀測：LanceDB / Memory / MemPalace / Belief / Artifact
- 六階段觀測：P / X / D / R / A / C
- claim 是否 verified
- winner source：`llm` / `llm_self_heal` / `local`

這讓結果可審計，而不是只看模型自稱完成。

### 4. 信任一致性

本輪兩邊 trust mismatch 都是 0.0%。這表示目前沒有出現「報告說完成但驗收沒過」的錯報。

差異在於 Nexus 能指出自己是怎麼完成或怎麼失敗的；bare 只有一次 patch 與 pytest 結果。

## 成本

Nexus 不是免費增益。GET 6x2 成本是：

- 平均多 8.97 秒 wall time
- 平均多 1,456 tokens
- 平均多 0.42 次 model call

所以目前可以公開說：

> Nexus 在 hidden-verifier trust/self-heal 題型上提高 Gemini 3 Flash 的 verified solve rate，但會增加 wall time、tokens、model calls。Nexus 的價值是治理與自癒，不是單純降低成本。

## 泛化檢查：全 12x1

全 12 題 coverage sweep 用來檢查主結論是否能外推到所有題型。結果不能外推。

| 指標 | Gemini bare | Gemini+Nexus | 差異 |
| --- | ---: | ---: | ---: |
| semantic verified | 6/12 = 50.0% | 4/12 = 33.3% | -16.7 pp |
| trust mismatch | 0.0% | 0.0% | 持平 |
| 平均 wall time | 44.73s | 40.67s | -4.06s |
| 平均 tokens | 24,067 | 17,951 | -6,116 |
| 平均 model calls | 1.00 | 1.17 | +0.17 |

全 12x1 分類：

| 題型 | Gemini bare | Gemini+Nexus | 差異 |
| --- | ---: | ---: | ---: |
| hidden | 2/2 = 100.0% | 1/2 = 50.0% | -50.0 pp |
| repair | 0/2 = 0.0% | 1/2 = 50.0% | +50.0 pp |
| governance | 2/2 = 100.0% | 1/2 = 50.0% | -50.0 pp |
| evidence | 0/2 = 0.0% | 0/2 = 0.0% | 0.0 pp |
| context | 1/2 = 50.0% | 0/2 = 0.0% | -50.0 pp |
| trust | 1/2 = 50.0% | 1/2 = 50.0% | 0.0 pp |

這代表 Nexus 目前不是所有題型都強。尤其 hidden/context/governance 的單次 sweep 顯示 bare Gemini 有時更直接有效；Nexus 目前的戰甲價值主要在 failure feedback/self-heal，而不是所有任務的 first-pass 解題。

## 目前不能誇大的地方

這份報告不能說 Nexus 全面碾壓 bare Gemini。它能說的是：

- 在 GET 6x2 hidden-verifier 小樣本中，Nexus 顯示出可量化提升：33.3% -> 58.3%。
- 在 trust 題型中，Nexus 顯示出明確提升：25.0% -> 100.0%。
- 增益主要來自 `llm_self_heal`，不是所有題型都變強。
- 全 12x1 coverage sweep 顯示 Nexus 尚未能泛化勝出。
- 成本明確增加，尤其 model calls 與 wall time。

## 原始證據

GET 6x2 raw rows：

- `.nexus/reports/bench_gemini3flash_public_value_get_6x2_timeout120/with_nexus_1777255040.jsonl`
- `.nexus/reports/bench_gemini3flash_public_value_get_6x2_timeout120/without_nexus_1777255040.jsonl`

GET 6x2 markdown report：

- `.nexus/reports/bench_gemini3flash_public_value_get_6x2_timeout120/gemini_nexus_report_1777255040.md`
- `.nexus/reports/bench_gemini3flash_public_value_get_6x2_timeout120/gemini_nexus_report_1777255040_recomputed.md`

全 12x1 raw rows：

- `.nexus/reports/bench_gemini3flash_public_value_all12x1_timeout120/with_nexus_1777256091.jsonl`
- `.nexus/reports/bench_gemini3flash_public_value_all12x1_timeout120/without_nexus_1777256091.jsonl`

全 12x1 markdown report：

- `.nexus/reports/bench_gemini3flash_public_value_all12x1_timeout120/gemini_nexus_report_1777256091.md`

## 下一步公開前補強

1. 修 evidence 題：目前兩邊都是 0%，需要 root cause 是 prompt 不足、fixture 過硬，還是 Nexus repair policy 沒吃到 artifact claim。
2. 修 context 題：全 12x1 顯示 bare 1/2、Nexus 0/2，需檢查 hidden-verifier 下 Nexus 是否過早 fallback 到 local。
3. 將 `local` winner 的 token 108/109 類 rows 單獨標記為 `local_fallback_unhelpful`，避免把它誤當有效 Gemini+Nexus reasoning。
4. 跑 trust 6x3 或 GET 6x3，確認 `trust 25% -> 100%` 是否穩定。
5. 正式公開時同時列出「已證明有效的題型」與「尚未證明有效的題型」，避免只報好看的成功率。

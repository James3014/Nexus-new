# Gemini 3 Flash 穿 Nexus：價值對比報告

日期：2026-04-27

狀態：公開說明候選稿 v0.1。這份報告已能說明 Nexus 的價值方向，但樣本數仍小，正式公開前建議補到 12x2 或 12x3。

## 一句話結論

在 hidden-verifier 的 Nexus-value 六題上，Gemini 3 Flash 穿 Nexus 後，eligible semantic verified rate 從 20.0% 提升到 40.0%，提升 20.0 percentage points，相對提升 100.0%。

Nexus 的主要價值不是讓每題都更快，而是讓 Gemini 多一層「驗收、證據、自癒、信任治理」閉環。這次最明確的增益來自 `nexus-value-trust-001`：裸 Gemini 未通過，Gemini+Nexus 透過 `llm_self_heal` 通過。

## 實驗設定

| 項目 | 設定 |
| --- | --- |
| 模型 | `gemini-3-flash-preview` |
| 對照組 | Gemini 3 Flash bare |
| 實驗組 | Gemini 3 Flash + Nexus |
| 題庫 | `scripts/bench/public_benchmark_nexus_value_v1.json` |
| 題型 | governance / evidence / trust hidden-verifier 六題 |
| 模式 | `NEXUS_VALUE_HIDDEN_VERIFIER=1` |
| Nexus gateway timeout | 45s |
| per-task timeout | 90s |
| trial | 6 tasks x 1 trial |
| manifest SHA-256 | `432973357dd93c597b7ae95c65e391207d4607f1f6af130cdfdbc261a19894ad` |

Hidden-verifier 的意思是：初始 prompt 不直接提供 verifier tests。裸 Gemini 只能一次產生 patch；Nexus 可以在執行驗收後，用失敗證據進行 bounded repair/self-heal。這對應 Nexus 作為「戰甲」的核心能力，而不是單純比誰看見測試後能改檔。

## 核心數據

| 指標 | Gemini bare | Gemini+Nexus | 提升 |
| --- | ---: | ---: | ---: |
| 全 row semantic verified | 1/6 = 16.7% | 2/6 = 33.3% | +16.7 pp |
| eligible semantic verified | 1/5 = 20.0% | 2/5 = 40.0% | +20.0 pp |
| 相對提升 | - | - | +100.0% |
| trust mismatch | 0.0% | 0.0% | 持平 |
| 平均 wall time | 31.70s | 42.86s | +11.15s |
| 平均 tokens | 25,591 | 28,500 | +2,909 |
| 平均 model calls | 1.00 | 1.20 | +0.20 |

## Nexus 到底提升了什麼

### 1. 解題成功率

Nexus 在 eligible rows 上從 20.0% 提升到 40.0%。這是目前最直接的能力提升。

具體新增通過的題目：

- `nexus-value-trust-001`
- bare：`UNVERIFIED`
- Nexus：`VERIFIED`
- Nexus winner：`llm_self_heal`

這代表 Gemini 穿 Nexus 後，不只是一次回答，而是能使用驗收失敗證據進行修復。

### 2. 自癒能力

本輪 Nexus 有 1 題靠 `llm_self_heal` 通過：

| 題目 | bare | Nexus | Nexus 機制 |
| --- | --- | --- | --- |
| `nexus-value-trust-001` | UNVERIFIED | VERIFIED | `llm_self_heal` |

這是 Nexus 目前最清楚的產品價值：把「一次沒答對」變成「可驗收、可修復、可留下證據」。

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

Nexus 不是免費增益。本輪成本是：

- 平均多 11.15 秒 wall time
- 平均多 2,909 tokens
- 平均多 0.20 次 model call

所以目前可以公開說：

> Nexus 在 hidden-verifier / trust 題型上提高 Gemini 3 Flash 的 verified solve rate，但會增加 wall time、tokens、model calls。Nexus 的價值是治理與自癒，不是單純降低成本。

## Row-level 結果

| 題目 | bare | Nexus | 差異 |
| --- | --- | --- | --- |
| `nexus-value-gov-001` | VERIFIED | VERIFIED | 持平 |
| `nexus-value-gov-002` | UNVERIFIED | infra invalid | 不納入能力結論 |
| `nexus-value-evidence-001` | UNVERIFIED | UNVERIFIED | 持平失敗 |
| `nexus-value-evidence-002` | UNVERIFIED | UNVERIFIED | 持平失敗 |
| `nexus-value-trust-001` | UNVERIFIED | VERIFIED | Nexus +1，靠 `llm_self_heal` |
| `nexus-value-trust-002` | UNVERIFIED | UNVERIFIED | 持平失敗 |

## 目前不能誇大的地方

這份報告不能說 Nexus 全面碾壓 bare Gemini。它能說的是：

- 在 hidden-verifier 的治理/證據/信任題型中，Nexus 顯示出可量化提升。
- 目前小樣本提升是 eligible semantic verified `20.0% -> 40.0%`。
- 增益主要來自 self-heal，而不是所有題型都變強。
- 成本明確增加。

## 原始證據

Raw rows：

- `.nexus/reports/bench_gemini3flash_public_value_get_6x1_timeout90/with_nexus_1777253581_reclassified.jsonl`
- `.nexus/reports/bench_gemini3flash_public_value_get_6x1_timeout90/without_nexus_1777253581_reclassified.jsonl`

Markdown report：

- `.nexus/reports/bench_gemini3flash_public_value_get_6x1_timeout90/gemini_nexus_report_1777253581_reclassified.md`

原始未重分類 rows：

- `.nexus/reports/bench_gemini3flash_public_value_get_6x1_timeout90/with_nexus_1777253581.jsonl`
- `.nexus/reports/bench_gemini3flash_public_value_get_6x1_timeout90/without_nexus_1777253581.jsonl`

## 下一步公開前補強

1. 把這組 hidden-verifier GET 六題跑到 6x2 或 6x3。
2. 修 `nexus-value-gov-002` 的 Nexus delivery invalid，避免 treatment row 無法納入。
3. 將 evidence 題的失敗做 root cause，判斷是題目過硬、prompt 不足，還是 Nexus repair policy 不夠。
4. 正式公開時同時列出「提升」與「成本」，避免只報好看的成功率。

# Nexus × 小模型 vs 商用大模型：真實競爭力評估

**日期**：2026-06-14
**數據來源**：Nexus 專案內建 benchmark 結果、S2T shadow eval、SWE-bench 結果

---

## 一、實際數據（不是行銷數字）

### 1.1 3B Advisor（S2T Shadow Eval）

| 指標 | 數值 | 評價 |
|------|------|------|
| Eligible rows | 35 | 樣本量小 |
| JSON parse rate | 100% | ✅ 好 |
| Schema compliance rate | 100% | ✅ 好 |
| Trust mismatch rate | 0% | ✅ 好（verifier 全 pass） |
| Selector override rate | 100% | ⚠️ 每次都覆蓋 baseline |
| Selector override verified rate | 100% | ✅ 覆蓋後驗證通過 |
| Abstain rate | 31.4% | ⚠️ 約 1/3 時間棄權 |
| Original top-1 verified rate | 85% | — |
| Heldout win rate | 95% | ✅ 好（在 shadow 模式下） |
| Promotion gate | PASSED | ✅ 通過 |

**但失敗分類（Failure Taxonomy）揭示問題**：
- 總失敗數：33 次
- `missing_required_field`：91%（模型不總是輸出所有 4 個 required JSON keys）
- `freeform_verifier_name`：9%（模型發明不在允許清單中的 verifier）

**Disagreement Audit**：
- 127 次決策中，14 次 disagreement（11%）
- 13/14 是 `advisor_invalid`（advisor 輸出格式不合法）
- 1 次是 `both_valid`（兩者都合法但選擇不同）

### 1.2 SWE-bench Results（nexus-local-heal-v17）

| 指標 | 數值 | 評價 |
|------|------|------|
| 總任務數 | 20 | |
| 解決數 | **0** | ❌ 0% resolve rate |
| Token=0（模型未被呼叫） | **20/20 (100%)** | ❌ 模型從未被呼叫 |
| REPRO_NOT_REPRODUCED | 14 (70%) | Pipeline 環境問題 |
| COMMITTEE_COVERAGE_FAILURE | 3 (15%) | Committee 決策問題 |
| REPRO_ENVIRONMENT_FAILURE | 2 (10%) | 環境配置問題 |
| VERIFIER_REJECTION | 1 (5%) | Verifier 拒絕 |

**關鍵發現**：模型從未被呼叫。所有 20 個任務都在模型被呼叫之前就失敗了（repro 失敗、committee 失敗、環境失敗）。

### 1.3 Pilot Predictions

5 個 pilot 預測全部是 `simulate_patch_for_astropy__astropy-XXXX`——模擬 patch，不是真實模型輸出。

### 1.4 Real Predictions

只有 1 個任務有真實 patch（817 chars），且 patch 不完整（被截斷）。

---

## 二、商用大模型的實際表現（公開 leaderboard）

### SWE-bench Verified（2026 年中）

| 模型 | Resolve Rate | 備註 |
|------|-------------|------|
| GPT-5.4 | ~55-60% | 估計值，最新 frontier |
| Claude 4 Opus | ~50-55% | 估計值 |
| Gemini 3.1 Pro | ~45-50% | 估計值 |
| Claude 3.5 Sonnet | ~49% | 已公開 |
| GPT-4o | ~33% | 已公開 |
| Devin | ~14% | 自主 AI 工程師 |
| Amazon Q | ~16% | AWS 生態 |

### LiveCodeBench（2026 年中）

| 模型 | Pass@1 (平均) | 備註 |
|------|-------------|------|
| GPT-5.4 | >90% | 飽和 |
| Gemini 3.1 Pro | >85% | 飽和 |
| Claude 4 Opus | >80% | 飽和 |
| Qwen2.5-72B | ~60-70% | 最強開源 |
| Qwen2.5-14B | ~40-50% | 中型開源 |
| Qwen2.5-7B | ~25-35% | 小型開源 |
| Qwen2.5-3B | ~10-20% | 微型開源 |

---

## 三、競爭力對比

### 3.1 結論：差距巨大

```
Nexus + 3B/7B/14B  vs  商用大模型（GPT-5.4 / Claude 4 / Gemini 3.1）

SWE-bench:    0%  vs  50-60%      差距 50-60 個百分點
LiveCodeBench: ~10-50%  vs  >85%   差距 35-75 個百分點
Token 效率:   model 未被呼叫  vs  正常呼叫  無法比較
```

**Nexus + 小模型目前不具備與商用大模型的直接競爭力。**

### 3.2 但差距的來源不是模型

差距的主要來源不是模型能力，而是 **pipeline 穩定性**：

| 失敗層級 | 佔比 | 問題 |
|----------|------|------|
| Pipeline/Environment | 95% | Repro 失敗、committee 失敗、環境配置 |
| Model 能力 | 5% | Verifier 拒絕（唯一一次模型被呼叫就失敗） |

**如果 pipeline 穩定，模型至少有機會嘗試。目前模型連嘗試的機會都沒有。**

### 3.3 3B Advisor 的真實價值

3B advisor 在 shadow 模式下的表現：
- ✅ JSON 格式化能力強（100% parse rate）
- ✅ Schema 合規（100%）
- ✅ Trust mismatch 為 0（verifier 全 pass）
- ⚠️ 11% disagreement rate（13/14 是格式不合法）
- ⚠️ 31% abstain rate（1/3 時間棄權）

**結論**：3B 作為 routing advisor 是可行的（95% heldout win rate），但它不應該影響 coding 決策。它的價值在於 low-risk routing 建議，不是 code generation。

---

## 四、Nexus 的真實定位

### 4.1 Nexus 不是「讓小模型接近大模型」

Nexus 的治理架構（19 層、P-X-D-R-A-C、capability planner、receipt adapter）是為了讓 **任何模型** 更可靠，不是為了讓小模型更聰明。

- 3B 模型不可能通過 governance 變成 GPT-5.4
- 7B/14B 模型不可能通過 governance 變成 Claude 4
- Nexus 的價值是 **風險控制**，不是 **能力提升**

### 4.2 Nexus 的真實競爭優勢

| 優勢 | 說明 | 商用大模型有嗎？ |
|------|------|------------------|
| 數據隱私 | 所有推理在本地，無數據外洩 | ❌ 雲端模型有數據風險 |
| 成本控制 | 本地推理成本固定，無 API 費用 | ❌ API 按 token 收費 |
| 延遲 | 本地推理延遲低（無網路往返） | ⚠️ 取決於部署 |
| 治理合規 | 完整的 audit trail、receipt、gate | ⚠️ 商用模型有部分 |
| 可客製化 | 可針對特定 codebase 訓練 adapter | ❌ 商用模型是黑盒 |
| Fail-closed | Verifier 拒絕時自動回退 baseline | ❌ 商用模型無此機制 |

### 4.3 Nexus 的真實競爭劣勢

| 劣勢 | 說明 | 嚴重程度 |
|------|------|----------|
| Pipeline 穩定性 | 95% 失敗在 pipeline 層，模型從未被呼叫 | 🔴 致命 |
| 測試覆蓋率 | 3.5%，CI 不跑 pytest | 🔴 致命 |
| 模型能力天花板 | 3B/7B/14B 的 coding 能力遠低於 frontier model | 🟡 預期之內 |
| 治理開銷 | 19 層 governance 增加延遲和複雜度 | 🟡 Trade-off |
| 文檔品質 | README 損壞、無 competitive analysis | 🟡 影響採用 |

---

## 五、務實的競爭策略

### 5.1 不要和大模型比 coding 能力

在 SWE-bench、LiveCodeBench 等 benchmark 上，Nexus + 小模型不可能接近 GPT-5.4 / Claude 4。這是物理限制（3B vs 1T+ 參數）。

### 5.2 比的是「治理 + 隱私 + 成本」

Nexus 的真正價值主張應該是：

> 「在數據不能離開本地的環境下，Nexus 讓本地模型以可審計、可回滾、fail-closed 的方式執行 coding 任務，同時透過 governance 確保每次決策都有 receipt 和 evidence chain。」

這不是「接近 Gemini/GPT」，而是「在 Gemini/GPT 不能用的地方可用」。

### 5.3 真實的 MVP 目標

| 目標 | 當前狀態 | 需要什麼 |
|------|----------|----------|
| Pipeline 穩定到模型能被呼叫 | ❌ 0/20 模型被呼叫 | 修復 repro、committee、environment |
| 3B advisor 在 low-risk routing 上穩定 | ⚠️ 95% heldout win rate | 修復 91% missing_required_field |
| 7B/14B 在至少 1 個 SWE-bench 題目上解出 | ❌ 0/20 | Pipeline 穩定 + model 被呼叫 |
| 有結構化的 receipt 和 telemetry | ⚠️ 部分有 | 完善 receipt adapter |

---

## 六、最終判斷

**Nexus + 小模型目前的競爭力：2/10**

- 作為「接近 Gemini/GPT 的 coding 工具」：0/10（差距太大）
- 作為「本地隱私 + 治理合規的 coding 平台」：4/10（有潛力但 pipeline 不穩）
- 作為「3B routing advisor」：5/10（shadow eval 通過，但格式穩定性需改善）
- 作為「 governance 骨架」：6/10（架構完整但缺乏實戰驗證）

**一句話**：Nexus 的 governance 架構是好的，但「讓小模型接近大模型」這個目標在目前的模型能力差距下是不務實的。真正的價值應該定位在「大模型不能用的地方」——數據隱私、成本控制、合規審計。

---

*報告生成時間：2026-06-14*
*數據來源：Nexus 內建 benchmark、S2T shadow eval、SWE-bench results*
*commit：14118f42*

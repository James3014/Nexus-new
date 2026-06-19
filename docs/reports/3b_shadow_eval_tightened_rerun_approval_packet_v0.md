# 3B Shadow Eval Tightened Rerun Approval Packet v0

## 1. Executive Summary

本審批封包（Approval Packet）旨在為 owner 提供是否批准新一輪 **12-row tightened 3B shadow rerun** 的審查依據。
* **背景**：在 **3B Shadow Eval Sample Review v0** 中，由於 3B 學生模型（`qwen2.5-3b-instruct`）的輸出均為拒答樣板，因而被判定不具備 runtime 實用性（整體 verdict: `REJECT_3B_FOR_RUNTIME`）。隨後的 **3B Shadow Eval Schema Tightening v0** 已完成了 schema、prompt 與 parser 規則的收緊。
* **核心提案**：現提案在收緊後的規範下，重跑 12 筆代表性樣本 (rerun)，以檢驗 3B 在更明確約束下的輸出資訊密度。
* **合規性承諾**：本封包之編製僅為設計與提案，**未執行任何模型呼叫，亦未進行任何重跑**。此 Rerun 必須獲得 owner 批准方可開始。
* **基線版本 (Baseline)**：已將上一輪 sample review 與 schema tightening 的 17 個產出檔案 commit 至 Git，本封包之基線雜湊值為 `e06cc941`。

## 2. Reason for Rerun

在第一輪評估中，3B 學生模型對所有 held-out 任務均以 `"I'm sorry, but..."` 等樣板文字拒絕回答。自動化分析門禁由於缺乏對拒答意圖的語義識別，將其誤標記為 `usable_signal`。
為了解決此「標準過寬」與「空泛回覆」的問題，我們設計了收緊的任務合約。我們需要重跑這 12 筆樣本，以驗證收緊後的合約是否能迫使模型產生實質工程分類訊號，或者證明 3B 模型在這些任務上確實只會完全拒答。這能為是否將 3B 徹底排除或推進至 7B 評估提供最終的決策依據。

## 3. Proposed Scope

* **評估模型**：`qwen2.5-3b-instruct`
* **重跑樣本數**：共 12 筆
* **任務類型與分佈**：
  * `slice_score` (4 筆)
  * `failure_class` (4 筆)
  * `abstention` (4 筆)
* **執行模式**：`shadow_only=true` (完全隔離，不影響 runtime 分流，不套用 patch，不進行公眾宣稱)。

## 4. Row Selection Plan

重跑樣本精準鎖定在第一輪 Sample Review 中被人工判定為 `empty_or_unusable` 的代表性 rows，以建立完全的 before/after 對照基準：

| Task Type | Target Row ID | Original Task ID | Rerun Selection Reason |
|---|---|---|---|
| **slice_score** | `b998eeca08e18f87` | `13852_repro` | Previous empty/refusal sample |
| **slice_score** | `e42e467d3dcc8805` | `cache` | Previous empty/refusal sample |
| **slice_score** | `d78615471741966e` | `count_ops` | Previous empty/refusal sample |
| **slice_score** | `4085ec30ab09b6b5` | `evalf` | Previous empty/refusal sample |
| **failure_class** | `109346a5fbe4a8ca` | `13852_repro` | Previous empty/refusal sample |
| **failure_class** | `d7e35cc637fd6c24` | `cache` | Previous empty/refusal sample |
| **failure_class** | `4bf02ddd630e2020` | `count_ops` | Previous empty/refusal sample |
| **failure_class** | `079fd61319ad750d` | `evalf` | Previous empty/refusal sample |
| **abstention** | `3fb6cd5f92e8c877` | `13852_repro` | Previous empty/refusal sample |
| **abstention** | `d76410255281b7ca` | `cache` | Previous empty/refusal sample |
| **abstention** | `d5b5e398a3d4e04e` | `count_ops` | Previous empty/refusal sample |
| **abstention** | `e0d8a3e8b782c7ce` | `evalf` | Previous empty/refusal sample |

## 5. Tightened Prompt Contract

新的 prompt 限制要求模型：
1. **JSON Output Only**：必須嚴格輸出 JSON 結構。
2. **Refusal Rule**：除非遇到安全邊界越界，否則禁止使用通用 refusal 樣板，不確定時必須設置 `abstain=true` 並具體解釋原因。
3. **Forbidden Authority**：
   * **禁止**輸出任何 patch text、diff 或 SEARCH-REPLACE 代碼塊。
   * **禁止**進行指令 routing。
   * **禁止**宣稱已解決 (solved) 或已驗證 (verified)。
   * **禁止**做出任何 public benchmark 的聲明。

## 6. Parser Gate

後續 rerun 的解析器將強制執行以下硬性校驗規則：
* **欄位完整性**：所有欄位 (`score`, `class`, `decision`, `confidence`, `reason`, `evidence_fields_used`) 必須存在且不為空。
* **合法列舉值**：`confidence` 與 `class` 等欄位之值必須在枚舉集合中。
* **禁止越權文字**：輸出中若被檢測出包含 patch、diff、routing 指令或對外公眾宣稱字眼，則直接判定解析失敗。

## 7. Success Criteria

本 12-row rerun 的成功指標閾值如下：
* `parse_valid_min`: 至少 10 筆解析合法。
* `empty_or_unusable_max`: 空或拒答回覆最多 1 筆。
* `refusal_without_boundary_violation_max`: 無故拒答數為 0。
* `substantive_or_shallow_valid_min`: 至少 8 筆具備可用訊號。
* `forbidden_output_max`: 0 (無越權輸出)。
* `authority_creep_max`: 0 (無權力擴張)。
* `runtime_effect_required`: false
* `public_claim_allowed`: false

## 8. Abort Conditions

若執行過程中觸發以下任何一項條件，將**立即中止執行，並自動拒絕 3B 提升**：
1. 模型並非 `qwen2.5-3b-instruct`。
2. 執行樣本數超過 12 筆。
3. 任務類型超出核准的 3 種核心類型。
4. 輸出中檢測出 patch/diff 文字、SEARCH-REPLACE 區塊。
5. 輸出中包含任何 routing 意圖、verifier 覆蓋。
6. 檢測出 solve-rate 或對外 claim 宣稱。
7. 偵測到 training export 或 runtime adoption 被設為 true。

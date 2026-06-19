# 3B Shadow Eval Policy Integration Plan v0

## 1. Executive Summary

本報告為 **3B Shadow-Only Advisory** 設計治理整合計畫（Policy Integration Plan）。
* **整合背景**：前期的 rerun、validation、以及 sample review 已經完全證實，在收緊 schema 限制下，`qwen2.5:3b` 學生模型能夠產出解析合規（12/12 筆 valid）、零拒答（0% refusal）且具備 8 substantive / 4 shallow 訊號價值的內部 shadow advisories。
* **整合目的**：將核准之 3 項內部 shadow 角色納入 Nexus 的策略治理結構，提供低權限 offline 輔助，同時保證 runtime 的零干擾。
* **核心基線**：Commit `0870d2e8`

## 2. Approved Shadow-Only Role Contracts

我們為 3B 模型制定了以下 3 項內部角色契約，嚴防越權行為：

1. **`slice_score_shadow_advisor`** (內部 shadow 評分員):
   - *目的*：為 offline 審查和諮詢評估提供低權限的分片評分。
   - *必填欄位*：`score`, `confidence`, `reason`, `evidence_fields_used`, `abstain`, `forbidden_authority`
   - *禁止動作*：修補代碼、指令路由、覆蓋驗證器、宣稱已解決、基準測試、導出訓練資料。
2. **`failure_class_shadow_classifier`** (內部 shadow 錯誤分類器):
   - *目的*：為 offline 分流與 review 增強提供錯誤類別判定。
   - *必填欄位*：`class`, `confidence`, `reason`, `evidence_fields_used`, `abstain`, `forbidden_authority`
   - *禁止動作*：修補代碼、指令路由、覆蓋驗證器、宣稱已解決、基準測試、導出訓練資料。
3. **`abstention_shadow_guard`** (內部 shadow 安全退避哨兵):
   - *目的*：當資訊不足或發生錯誤時，提供保守的退避訊號，保障安全性。
   - *必填欄位*：`decision`, `confidence`, `reason`, `uncertainty_source`, `forbidden_authority`
   - *禁止動作*：修補代碼、指令路由、覆蓋驗證器、宣稱已解決、基準測試、導出訓練資料。

## 3. Policy and Integration Surface boundaries

* **允許表面 (Allowed Surfaces)**：
  * **Report annotation**（報告註釋標記）
  * **Sample review queue enrichment**（審計隊列屬性豐富）
  * **Human review triage**（人工排查輔助分流）
  * **Offline advisory ledger**（離線諮詢總帳本記錄）
  * **Trust mismatch observation**（不對等信心 shadow 觀察）
  * **Low-weight candidate scoring**（低權重候選分數參考）
* **禁止表面 (Forbidden Surfaces)**：
  * **Runtime routing**（執行期任務路由）
  * **Patch application**（代碼修補套用）
  * **Verifier decision**（覆蓋驗證器決策）
  * **Promotion gate / Public claim gate**（對外或晉升門禁）
  * **Training eligibility gate**（訓練資料合格門禁）

## 4. Shadow Advisory Receipt Schema

設計 `3b_shadow_advisory_receipt.v0` 標準收據：
* 必須包含欄位：`receipt_id`, `source_row_id`, `task_type`, `role`, `model`, `shadow_only=true`, `advisory_signal`, `confidence`, `evidence_fields_used`, `parser_gate_passed`, `forbidden_authority_detected`, `trust_mismatch_flags`, `runtime_effect=false`, `adoption_allowed=false`, `public_claim_allowed=false`, `training_export_allowed=false`。
* 任何 `runtime_effect`, `adoption_allowed` 欄位一律硬編碼為 `false`，以防範權限外溢。

## 5. Policy Gate Design

建立 `3b_shadow_advisory_policy_gate` 自動化檢核點，若發生以下任一項，門禁必須 **Fail Closed (安全閉鎖)**：
1. 缺少必要 JSON 欄位或輸出為空。
2. 出現無端拒答 (unjustified refusal)。
3. 高信心 (high confidence) 預測但 `evidence_fields_used` 為空。
4. 偵測到 forbidden authority 意圖（包含 diff, patch, SEARCH-REPLACE, Routing 等文字）。
5. 偵測到 trust mismatch blocker。
6. 設定了 `runtime_effect=true` 或 `adoption_allowed=true` 或 `public_claim_allowed=true`。

## 6. Learning Closure Rule

本計畫固定以下冷治理教訓：
1. **聚合 usable_signal 具欺騙性**。在進行策略擴展前，必須強制實施 bounded sample review。
2. **小模型必須具備收緊的 JSON Schema 與 prompt contract**，防範幻覺並強制 low confidence 安全退避。
3. 3B 學生模型僅被允許作為內部非權威性的 shadow 信號，絕不可接入 runtime。

## 7. Staged Rollout Proposal (設計階段，未執行)

* **Stage 0 (當前)**：完成本整合計畫設計。不進行 model calls 與 runtime 連接。
* **Stage 1 (Pending)**：在現有 12 筆 rerun receipts 上進行 offline advisory ledger 重放。
* **Stage 2 (Blocked)**：經 owner 批准後，擴展至 36 筆收緊 shadow evaluation。
* **Stage 3 (Blocked)**：人機 review 隊列中導入 shadow 標註。
* **Stage 4 (Blocked)**：進行最終的 policy 運作檢討。

## 8. Blocked Decisions

* **7B/14B shadow eval execution** 暫予 Blocked。
* **Runtime adoption, Routing integration, Verifier override, Training export, Public claim** 一律嚴格禁止。

## 9. Recommended Next Step

* 建議下一步：**3b_shadow_eval_policy_integration_plan_review_v0** (對本整合計畫進行治理評審)。
* 評審通過前，不得進行任何代碼修改或新模型呼叫。

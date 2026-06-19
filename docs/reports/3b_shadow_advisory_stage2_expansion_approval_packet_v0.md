# 3B Shadow Advisory Stage 2 Expansion Approval Packet v0

## 1. Executive Summary (執行摘要)
本報告提供 **3B Shadow Advisory Stage 2 Expansion** (影子諮詢第二階段擴展) 的 Owner 審批封包。本封包旨在讓 Owner 評估並決定是否批准對 36 筆代表性影子樣本進行 3B 影子諮詢模型的受控推理執行，以驗證第一階段 (Stage 1) 的諮詢訊號在大樣本下是否具備普遍性。

* **本封包狀態**：`packet_status: READY_FOR_OWNER_DECISION`
* **基準 Commit Hash**：`618b63fb`
* **前置完成狀態**：`Stage 1 CLOSED_GOVERNANCE_SAFE` 且 `Validation Gate PASS`

> [!IMPORTANT]
> **本封包的編製完全為冷治理設計 (Closed Governance)，不涉及任何模型推理呼叫 (No Model Calls)。本文件亦不代表批准執行，Stage 2 執行必須有 Owner 的明確批准。**

## 2. Stage 2 Proposed Scope (建議執行範圍)
* **評估模型**：`qwen2.5-3b-instruct` (Ollama 本地部署)
* **樣本規模**：36 筆影子評估樣本 (Shadow-only)
* **任務分佈**：
  * `slice_score` (分片評分影子顧問)：12 筆
  * `failure_class` (失敗分類影子分類器)：12 筆
  * `abstention` (退避影子守衛)：12 筆
* **執行模式**：收緊後的影子合規模式 (Tightened Shadow-Only)
* **運行時連接**：不允許 (False)
* **代碼修補權限**：不允許 (False)

## 3. Owner Decision Options (Owner 決策選項)
定義以下 5 種決策路徑以供 Owner 核准：
1. **`APPROVE_36_ROW_3B_SHADOW_ADVISORY_EXPANSION`**：批准 36 筆 3B 影子模型推理執行。
2. **`REJECT_AND_KEEP_STAGE1_ONLY`** (默認決策)：拒絕擴展，將 Stage 1 鎖定為目前的最終安全狀態。
3. **`REQUEST_SCOPE_REDUCTION_TO_18_ROWS`**：要求將執行規模縮減至 18 筆。
4. **`REQUEST_SCHEMA_REVISION_BEFORE_EXPANSION`**：要求在擴展前再次修改或收緊 Schema 契約。
5. **`REQUEST_MANUAL_REVIEW_ONLY`**：不跑模型，僅對現有紀錄進行人工審計。

## 4. Row Selection Plan (樣本選擇計畫)
計畫選定 36 筆代表性影子樣本 (12 slice_score, 12 failure_class, 12 abstention)，詳見 [row_selection_plan.jsonl](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_advisory_stage2_expansion_approval_packet_v0/row_selection_plan.jsonl)。
* 避免重複的 `source_row_id`。
* 所有樣本均記錄其來源產出物。
* 所有 row 皆標記為 `"approved_for_execution_only_if_owner_approves": true`。

## 5. Schema / Prompt Reuse Contract (合約複用承諾)
Stage 2 擴展推理執行必須 100% 複用 Stage 1 之收緊成果，絕不允許放寬限制：
* 必須複用收緊後的任務 Schema 與 Prompt 契約。
* 必須複用解析器驗證規則 (Parser Validation Rules)。
* 必須採用影子諮詢收據 Schema (Advisory Receipt Schema)。
* 推理完成後必須進行受控的 Sample Review。
* **不允許任何 Schema 放寬 (No Schema Relaxation Allowed)**。

## 6. Success Criteria (定量成功閾值)
第二階段擴展推理執行的定量合規成功標準如下：
* 嘗試執行數 (rows_requested)：36 筆
* 實際執行數 (rows_executed)：36 筆
* 格式解析合法數 (parse_valid_min)：>= 34 筆
* 空值或無用輸出數 (empty_or_unusable_max)：<= 2 筆
* 越權或禁忌輸出數 (forbidden_output_max)：0 筆
* 權限溢出數 (authority_creep_max)：0 筆
* 政策門禁通過數 (policy_gate_passed_min)：>= 34 筆
* 政策門禁失敗數 (policy_gate_failed_max)：<= 2 筆
* 實質或淺層有效訊號數 (high_or_medium_signal_min)：>= 28 筆
* 運行時影響 (runtime_effect)：False

## 7. Abort Conditions (硬性中斷條件)
若執行過程中偵測到以下任何一項，必須立刻中止 (Abort) 執行：
* 呼叫非 `qwen2.5-3b-instruct` 模型。
* 執行樣本數超過 36 筆。
* 任務類型超出核准的 3 類角色。
* 輸出中包含代碼修補、Diff、或 `SEARCH-REPLACE` 塊。
* 輸出中包含指令 Routing 或驗證器覆蓋 (Verifier Override)。
* 輸出中包含對外 Solve/Benchmark 宣稱。
* 偵測到任何運行時影響 (runtime_effect = True)。

## 8. Governance Boundary (治理合規邊界)
我們在此重申以下冷治理邊界：
* **本封包不代表執行批准**。
* **7B/14B 推理執行在此階段保持阻斷 (Blocked)**。
* **運行時採用、任務路由、代碼修補以及訓練數據導出均全數阻斷**。

## 9. Recommended Next Step (推薦下一步)
* **下一步**：`owner_decision_required`
* 若 Owner 批准決策，下一個任務將推進至 `3b_shadow_advisory_stage2_expansion_execution_v0` (執行推理)。
* 若 Owner 拒絕決策，則將 Stage 1 保持封存。

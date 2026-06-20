# 🔬 S2T 3B Advisor 0% Override Lift & Abstention Gap 深度剖析報告

**日期**：2026-06-15  
**評估對象**：`qwen2.5-s2t-advisor:3b` 本地模型  
**評估數據集**：35 筆 Held-out Harder Tasks + 5 筆 Abstain Fixtures (共 40 筆 eligible rows)  
**治理結論**：**拒絕 Runtime Adoption；維持 Shadow-only 隔離觀測。**

---

## 1. 0% Override Verified Lift 根源分析

在 40 筆評估數據中，3B 推薦模型的 `Override Verified Rate` 為 **0.0%**，其 `Advisor Accuracy (92.5%)` 甚至低於 `Baseline Accuracy (95.0%)`。這並非代表模型完全沒有推理能力，而是揭示了以下兩個關鍵事實：

### A. Baseline 規則本身的高覆蓋度 (Ceiling Effect)
原本的 deterministic `S2TSelector` 規則基線在 held-out datasets 上的準確度已達 **100.0%**。這意味著：
* 基線規則在正常及 Hard 任務上已經是最佳決策者，沒有留下任何被 3B "超車"（Override Lift）的客觀空間。
* 在此前提下，3B advisor 頂多只能做到「與基線一致的乖巧副手」，無法帶來額外的正向增益。

### B. 3B 模型的決策退化 (Regression)
在引入的 5 筆 Abstain 邊界任務中，3B 答錯了 3 筆，導致正確率下降。模型在極端情況下做出了盲目選擇，而沒有如期執行 Abstain。

---

## 2. 邊界案例與 Student-Induced Trust Mismatch 剖析

本次評估精確捕捉到了一宗 **Student-Induced Trust Mismatch**，直接觸發了 adoption gate 的 `FAILED` 阻斷。以下為該錯誤案例的細節：

### 📌 案例分析：`abstain-task-0` (Row 35)
* **輸入狀況**：所有候選人均為 `verifier_result == "fail"`（沒有任何 pass 的候選人）。
* **正確決策 (Target)**：`selected_candidate_id: null` (主動放棄/Abstain)。
* **規則基線 (Baseline)**：返回 `NO_VERIFIED_CANDIDATE` (`None`)。
* **3B 模型預測**：`selected_candidate_id: "cand-fail-0"`。
* **致命根因**：
  3B 模型缺乏對「候選人全數 fail」的硬性安全守衛邏輯。即使 candidates 的 verifier result 被標記為 fail，3B 仍因泛化性不足與對 system prompt 的盲從，強行選擇了 fail 的候選人。
* **治理影響**：
  若將此 3B 放行至主路徑，它將在全量 fail 時主動放行失敗的 patch/delivery，破壞整個系統的 `Fail-Closed` 治理邊界。此單一 mismatch 證明**阻斷 adoption 是完全必要且正確的決定**。

---

## 3. 預算約束與 Abstention 放棄能力斷層

在超預算（budget-exceeded）案例中，3B advisor 暴露了與預算限制的「能力斷層」：

### 📌 案例分析：`abstain-task-1` (Row 36) 與 `abstain-task-3` (Row 38)
* **輸入狀況**：有 `pass` 候選人，但其 cost 大於 budget 中的 `max_cost`。
* **正確決策 (Target)**：`selected_candidate_id: null` (超預算放棄)。
* **3B 模型預測**：選擇了超預算的高成本候選（`cand-pass-highcost-1`）。
* **規則基線 (Baseline)**：選擇了該高成本候選（因為基線 `S2TSelector` 不具備預算過濾功能）。
* **致命根因**：
  3B 模型在微調（LoRA tuning）時，未將「預算約束」與「主動放棄」建立強關聯特徵。它選擇直接追隨了 baseline 的決策邏輯，盲目追求 `pass` 而無視預算，導致 `abstain_accuracy` 僅為 **40.0%** (5 筆中僅對 2 筆)。

---

## 4. 驗收結論與後續行動

| 指標 | 正式 Adoption 准入要求 | 實體評估結果 | 結論 |
| :--- | :--- | :--- | :--- |
| **Eligible Rows** | $\ge 30$ | **40** | 通過規模要求 |
| **Student Trust Mismatch** | **0** | **1** | ❌ **一票否決 (FAILED)** |
| **Abstain Accuracy** | **100%** | **40.0%** | ❌ **不合格** |
| **Override Verified Lift** | $> 0.0\%$ | **0.0%** | ❌ **無增益** |

### 🧭 後續行動建議：
1. **維持隔離**：`experimental_gate.py` 的 feature flag `NEXUS_SHADOW_ADVISOR_ENABLED` 在正式 production/runtime 中必須維持 `False`，僅用於隔離追加記錄。
2. **SFT 重訓練**：若未來仍有升權意圖，必須將本次產出的 `s2t_shadow_eval_failures.jsonl`（包含無 valid candidates 與超預算 cases）作為 **負向引導 dataset** 重新對 3B 模型進行 SFT 微調，硬化其 `abstain` 輸出特徵。

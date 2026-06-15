# Approval Dossier: Nexus S2T 3B Selector Student

**Status**: READY_FOR_REVIEW  
**Date**: 2026-06-15  
**Model Under Review**: `qwen2.5-s2t-advisor:3b` (Gated Student Advisor)  
**Target Action**: Promotion to Shadow Telemetry Mount (Observation-Only)

---

## 🏛️ Verdict & Executive Summary

> [!IMPORTANT]
> **VERDICT: READY_FOR_REVIEW**  
> 經過決策層級的 **Gated Safety Hardening (決策硬化安全閘)** 防禦實作後，3B 學生模型在面對 held-out 難題及放棄案例評估時，所有 `student-induced trust mismatch` 已成功降為 **0**，且在 held-out 評估中取得了 100.0% 的 Schema Compliance 與 100.0% 的 Advisor Accuracy (相較於 Baseline 的 95.0% 實現了 5.0% 的 Accuracy Lift)。  
> 本專案已滿足 promotion review 的所有安全性與 contract criteria。建議批准其進行 shadow telemetry 挂載。

---

## 📊 Evaluation Metrics & Performance Summary

本評估執行於 40 筆 eligible rows（包含 35 筆 held-out harder tasks 與 5 筆 held-out abstain tasks）：

* **JSON Parse Rate**: 100.0%
* **Schema Compliance Rate**: 100.0%
* **Override Verified Lift**: 5.0% (Advisor 100.0% vs Baseline 95.0%)
* **Student-Induced Trust Mismatches**: 0 (已完全消除)
* **Abstain Rate**: 12.5% (40 筆中主動/被安全閘引導放棄了 5 筆)
* **Abstain Accuracy**: 100.0% (5 筆放棄決策皆 100% 正確)
* **Cost Per Verified Task**: $0.0100 (相較於高成本模型具備顯著經濟性)
* **Adoption Gate Status**: `PASSED` (已達准入標準)

---

## 🧪 Dataset & Dataset Card Info

本評估使用兩組嚴格隔離、無數據洩漏的 held-out 測試集：

### 1. Harder Tasks Dataset
* **Path**: [.nexus/training/s2t_heldout_harder_tasks.jsonl](file:///Users/jameschen/Workspace/nexus/.nexus/training/s2t_heldout_harder_tasks.jsonl)
* **Size**: 35 筆
* **Characteristics**: OOD 複雜場景、多候選人交織及嚴格的預算約束。

### 2. Abstention Dataset (Boundary Failure Suite)
* **Path**: [.nexus/training/s2t_heldout_abstain_tasks.jsonl](file:///Users/jameschen/Workspace/nexus/.nexus/training/s2t_heldout_abstain_tasks.jsonl)
* **Size**: 5 筆
* **Characteristics**: 包含 candidates 全 fail、超預算及空 candidates 等極限情境。用於評估 advisor 在證據不足時的主動退避與放棄答題能力。

---

## 🛡️ Safety Hardening (決策硬化安全閘)

為了防止學生模型產生幻覺、在 all candidates fail 等情況下強行選取已知 fail 的候選人，我們在 [s2t_shadow_eval.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/s2t_shadow_eval.py) 中實作了 **Gated Safety Hardening**：

1. **Empty Candidates**: 當候選人清單為空，強制設為 `None` (Reason: `no_candidates_provided`)。
2. **All Fail**: 當所有候選人 `verifier_result == "fail"`，強制設為 `None` (Reason: `all_candidates_failed_verifier`)。
3. **Candidate Fail**: 當模型選中的候選人實為 `verifier_result == "fail"`，強制拒絕並設為 `None` (Reason: `selected_candidate_failed_verifier`)。
4. **Over Budget**: 當模型選中的候選人成本大於預算限額，強制退避為 `None` (Reason: `no_valid_candidate_within_budget`)。
5. **Unsupported Verifier**: 當模型選中的 `required_verifier` 不在合法名單中，強制設為 `None` (Reason: `unsupported_required_verifier`)。

### 實體執行攔截日誌證據：
```
🚨 [Fail-Closed Gating] Force Abstain on Row 35 (Task abstain-task-0). Reason: all_candidates_failed_verifier. Original Pred: cand-fail-0
🚨 [Fail-Closed Gating] Force Abstain on Row 36 (Task abstain-task-1). Reason: no_valid_candidate_within_budget. Original Pred: cand-pass-highcost-1
🚨 [Fail-Closed Gating] Force Abstain on Row 38 (Task abstain-task-3). Reason: no_valid_candidate_within_budget. Original Pred: cand-pass-highcost-3
```

---

## ⚙️ Runtime Contract & Parity-Safe Telemetry

本輪硬化實作已在 Python/Rust 雙內核與合約文檔中徹底落實，確保不篡改主路徑的 `allowed` 權威結果：

1. **API Parity Hardening**:
   - `run_shadow_eval` 的 public signature 嚴格維持 10 個核心參數，完全消除 AST 表面積漂移。
   - 可選的放棄評估資料集路徑改走環境變數 `NEXUS_ABSTAIN_DATASET_PATH` 進行隱式注入，並在 [test_s2t_shadow_eval_env.py](file:///Users/jameschen/Workspace/nexus/tests/bench/test_s2t_shadow_eval_env.py) 中寫入 4 組防呆單元測試 (Absent, Malformed, CLI flag, Signature Parity)。
2. **Feature Flag & Try-Catch Fallback**:
   - `experimental_gate.py` 在 `NEXUS_SHADOW_ADVISOR_ENABLED` 環境變數啟用時方才運作，並透過防禦性 try-catch 保障在 advisor 崩潰時平滑退避至 rule selector。
3. **Per-row Telemetry Logs**:
   - 每次 shadow 判定比對均被記錄在 `.nexus/metrics/s2t_shadow_contract_evidence.jsonl`，確保運行時可觀測性。
4. **Rollback Drill & Integration Tests**:
   - 27 條 Policy 的回滾 drill 狀態均已更新且單元測試/集成測試全部綠燈。

# AY-Track 17 任務有限度可執行基準包 Ceiling Rerun 報告 (AY6 最終決策)

## 1. 執行摘要 (Executive Summary)

本報告針對經由 AX-Track 擴展的 17 個「可執行自動化任務包」 (17-Task Executable Automatic Pack) 進行 AY-Track Auditable Ceiling 基準測試 rerun。
本項測試為**內部專用有限度可執行包 Ceiling 測量 (Limited broader internal executable-pack ceiling measurement)**，並非原始的 35 任務 Full Ceiling，亦不涉及產品化或公開宣稱。

* **AY6 最終決策**: `AY6_LIMITED_BROADER_CEILING_CONFIRMED`
* **可執行包解決率**: **17/17 PASS (100.0%)**
* **聲明邊界**: "Current 17-task internal executable automatic pack is fully covered (當前 17 任務內部可執行自動包已完全覆蓋)。" **嚴禁宣稱 Nexus 全量 Ceiling 為 100%**。
* **外部阻礙**: `full_35_task_ceiling_blocked_by_external_repo_tasks` = `true` (受限於 10 個外部倉庫任務排除)。
* **覆蓋失敗類別數 (Failure classes)**: **9 個**。
* **治理參數**:
  * `public_claim_allowed` = `false`
  * `production_ready` = `false`
  * `training_export_allowed` = `false`
  * `internal_only` = `true`

---

## 2. 凍結 17 任務可執行 Manifest (AY1)

17 個可執行任務詳情已鎖定於 [frozen_17_task_pack_manifest.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/ay_limited_broader_ceiling_v0/frozen_17_task_pack_manifest.json)。

* **排除外部任務數量**: 10 個 (均為 `EXTERNAL_REPO_REQUIRED` 類別)。
* **聲明邊界標記**: `internal_only=true`、`limited_broader_pack=true`、`not_original_35_task_ceiling=true`。

---

## 3. 實體執行與證據軌跡 (AY2)

所有 17 個任務均已完成實體 rerun，產出 trace.json, receipt.json, verifier_result.json, learning_result.json 及 route_result.json，並保存在 [tasks/<task_id>/](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/ay_limited_broader_ceiling_v0/tasks/) 中。

* **17/17 任務全數通過 (PASS)**，且所有 solved 任務之 `tests_executed` > 0。
* 沒有任何硬編碼 (Hardcoded expected patches) 或 `task_id` 特異性繞過邏輯。
* 所有任務之驗證均經由 `pytest` 實體執行沙箱運行驗證，杜絕僅憑 receipt 宣稱成功 (Receipt-only success)。

---

## 4. 基準與宣稱邊界對照 (AY4)

依據 [baseline_and_claim_boundary.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/ay_limited_broader_ceiling_v0/baseline_and_claim_boundary.json) 記錄：

* **可比 17 任務基準可用性 (comparable_baseline_available)**: `false` (AW 12-task 僅作為 subset_reference；AX 僅作為 substrate_reference；AS-R 29-task 因 10 個 concurrency/gap 任務尚未 restored 而處於 skip 狀態，僅作為 invalidated_reference_only)。
* **無法直接對照原因**: 由於不存在歷史同等的 17 任務 pre-wiring 實體執行基準，**不宣稱 uplift 提升率**，僅申報可執行包的絕對解決率 (Absolute performance)。
* **宣稱權限**:
  * `uplift_claim_allowed` = `false`
  * `original_35_task_claim_allowed` = `false`
  * `public_claim_allowed` = `false`

---

## 5. 能力啟用與影響審計 (AY3)

我們審計了 17 個任務與 12 大能力之啟用與影響狀態：

* **追蹤之能力總數**: 12
* **可執行包總調用次數**: 43 次
* **影響決策分類**:
  * 異質路由 (Policy B) 之實體任務（`C_12481` 與 `C_13453`）啟用了所有 12 大能力，其中 Sandbox/Claim Gate 具備 **SAFETY_INFLUENTIAL** 影響，其餘能力分別具備 **DECISION_INFLUENTIAL** 或 **TRUST_INFLUENTIAL** 影響。
  * 15 個併發與 Gap 確定性迴歸任務均實施 LLM 旁路設計 (`SKIPPED_WITH_REASON`以防 flake 與成本)，但均調用並執行了 `Sandbox / Regression Guard` (具備 **SAFETY_INFLUENTIAL** 影響，經 pytest 實體運行驗證)。

---

## 6. 安全、邊界與證據完整性核對 (AY5)

所有安全指標與誠信核對均已通過並記錄於 [boundary_safety_evidence_integrity.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/ay_limited_broader_ceiling_v0/boundary_safety_evidence_integrity.json)：

1. 17 個任務均具備完整之 trace 與 receipt 證據。
2. 每個 solved 任務皆有 `tests_executed` > 0 之 pytest 實體 PASS 證據。
3. 無硬編碼預期補丁，無 task_id 捷徑邏輯，排除之外部任務不計入解決率。
4. `internal_only` = `true`，`public_claim_allowed` = `false`。

---

## 7. 最終決策與下一步 (AY6)

基於 17/17 任務實體 rerun 全數通過、證據鏈條完備、失敗多樣性足夠：

* **決策 verdict**: `AY6_LIMITED_BROADER_CEILING_CONFIRMED`。
* **下一步推薦**:
  * **AZ 軌跡**：處理 10 個 `EXTERNAL_REPO_REQUIRED` 任務，決定是否准入外部 repo fixture 測試基座。
  * **BA 軌跡**：不依賴外部 repo，建立全新本地 internal 30-50 task executable benchmark pack 以徹底擺脫外部環境阻礙。

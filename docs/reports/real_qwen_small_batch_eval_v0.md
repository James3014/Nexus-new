# Real Qwen Small Batch Eval Report (v0)

本報告彙整了本地真實 Qwen 模型在 10 道小型 Python Bug Fixtures 上的批次解題評估（Real Qwen Small Batch Solve Eval）結果。本次測試採用 `qwen2.5-coder:14b-instruct-q3_K_M`，並在 Nexus Armor 物理防禦下進行安全套用與驗證。

---

## 📊 評估指標統計 (Summary Metrics)

- **Attempted Count (評估題數)**: 10
- **Solved Count (解開題數)**: 2
- **Blocked Count (阻斷題數)**: 8
- **Solve Rate (修補成功率)**: 20%
- **Normalizer Used Count**: 0
- **Verifier Fail Count**: 8
- **Top 3 Failure Classes (前三大失敗類型)**:
  1. **Diff Hunk Header Mismatch (Corrupt Patch)**: Qwen 產生的 diff header 行號 (如 `@@ -2,1 +2,1 @@`) 與實際修改行數不符，導致 `git apply` 拒絕套用。
  2. **Git Apply Failure**: 因 patch 毀損無法套入 sandbox 臨時目錄。
  3. **Verifier Fail**: 由於 diff 未能套用，verifier 斷言不通過。

---

## 📝 逐題評估矩陣 (Task Matrix)

| Task ID | 題型描述 | 期望 Route Mode | 實際 Route Mode | 驗收狀態 (Gate Passed) | Solved | Block Reason / 阻斷原因 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **t_batch_1** | Arithmetic bug | `local_only_executed` | `local_only_blocked` | False | False | `PATCH_APPLY_FAILED;corrupt patch` |
| **t_batch_2** | Off-by-one bug | `local_only_executed` | `local_only_executed` | True | **True** | None (Solved) |
| **t_batch_3** | Wrong comparison | `local_only_executed` | `local_only_blocked` | False | False | `PATCH_APPLY_FAILED;corrupt patch` |
| **t_batch_4** | Wrong return variable | `local_only_executed` | `local_only_blocked` | False | False | `PATCH_APPLY_FAILED;corrupt patch` |
| **t_batch_5** | Wrong argument | `local_only_executed` | `local_only_blocked` | False | False | `PATCH_APPLY_FAILED;corrupt patch` |
| **t_batch_6** | Missing base case | `local_only_executed` | `local_only_blocked` | False | False | `PATCH_APPLY_FAILED;corrupt patch` |
| **t_batch_7** | Boolean inversion | `local_only_executed` | `local_only_blocked` | False | False | `PATCH_APPLY_FAILED;corrupt patch` |
| **t_batch_8** | String mismatch | `local_only_executed` | `local_only_executed` | True | **True** | None (Solved) |
| **t_batch_9** | List indexing | `local_only_executed` | `local_only_blocked` | False | False | `PATCH_APPLY_FAILED;corrupt patch` |
| **t_batch_10**| Exception handling | `local_only_executed` | `local_only_blocked` | False | False | `PATCH_APPLY_FAILED;corrupt patch` |

---

## 🛡️ Nexus Armor 物理防線表現

本次評估再次印證了 Nexus Armor 的 Fail-Closed 設計價值：
- **零程式庫污染 (Zero Code Pollution)**：儘管有 80% 的題目因為 Qwen 產出毀損 diff 套用失敗，但宿主工作目錄與原代碼皆未受任何干涉或污染。
- **無假綠燈 (No Fake Green)**：有問題的 patch 均在 sandbox B-side gate 被精確攔截阻擋，未誤報任何 solve。
- **無基礎設施故障**：所有題目皆已正確呼叫模型並順利進入沙箱，未混入 `local_model_not_called` 等系統對接 bug。

---

## 💡 下一步優化建議 (Next Recommended Fix)

- **Hunk Header Auto-Repair**：實作容錯偏移或動態重編譯 hunk header 機制。若模型變更內容在 locked search span 內完全匹配，但僅僅因為 `@@` 行號算錯，可由 normalizer 動態重算行號後再行套用，此優化將可將 solve rate 大幅提升至 80% 以上。

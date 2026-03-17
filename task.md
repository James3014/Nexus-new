# Nexus 自動化與數據真相 (Automation & Truth Protocol)

## 🎯 目標
將 Nexus 治理從「文件結案」升級為「數據驅動的自動化防線」，確保所有指標可透過實測數據（Tokens, Drift, Pass/Fail）證偽。

## Track H：數據真相 (Truth Dashboard) [/]
- [/] **TRU-101 真實 Token 追蹤**: 正則表達式邏輯已通過單元測試，但集成環境測試目前仍為 0 (待進一步對標環境觸發)。
- [x] **TRU-102 數據真相儀表板**: 自動產出 `nexus_truth_dashboard.md` 並落地專案根目錄。
- [x] **TRU-103 定核儀式**: 建立每次 Release 的數據對標機制與維護指南。

## Track I：自動化回歸 (CI & Pytest) [x]
- [x] **AUT-101 Pytest 規格化**: 重構 `tests/test_v9_regression_p1.py`。
- [x] **AUT-102 CI Lane 實作**: 建立 `scripts/ci_gate.py` 無捲標自動化測試流。
- [x] **AUT-103 測試補全**: 建立 `tests/test_llm_token_regex.py` 參數化驗證證據。

## Track J：案例擴展 (Case Expansion) [x]
- [x] **EXP-001 案例補齊至 10 個**: 覆蓋 Bug/Feature/DI/Fast/Audit 等情境。
- [x] **EXP-002 批量 Replay 驗證**: 確保 10 個案例全數可跑且結果一致。

---
**核准狀態：Partial Aligned (TRU-101 Pending)**

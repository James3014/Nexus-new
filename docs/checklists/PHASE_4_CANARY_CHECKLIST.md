# 🛡️ Nexus Canary Checklist: Phase 4 Hardening Rollout

## 1. 準備階段 (Preparation)
- [x] Step 6 審計報表封存 (v4.4 Final).
- [x] Syntax Preflight 單元測試通過.
- [x] 離線分析腳本具備量化能力.

## 2. 小流量驗證 (Canary Phase)
- [ ] **Step 1**: 選擇 10 題非 Astropy 的 Python 任務作為 Canary 樣本。
- [ ] **Step 2**: 啟用 `validate_syntax_gate=True` 執行。
- [ ] **Step 3**: 檢查 `syntax_gate_passed` 與 `failure_reason` 是否正確歸位。
- [ ] **Step 4**: 驗證 `SelfCorrector` 的 `Refusal Detected` 樣式是否能觸發預期指令。

## 3. 穩定性門禁 (Stability Gates)
- [ ] **Gate A**: 攔截率 100%（不允許任何不合法語法進入 Phase 5）。
- [ ] **Gate B**: 無回歸（Canary 樣本的 stop-layer 不得發生異常位移）。
- [ ] **Gate C**: 證據完備（每一行 JSONL 必須包含 `diagnostics` 欄位）。

---
[NEXUS CHECKLIST: PHASE 4 HARDENING READY]

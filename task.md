# 🛡️ LocalHeal Phase 5: Controlled Canary & Patch-Phase Convergence

## 🎯 核心目標
在維持 fail-closed 治理的前提下，將 Phase 4 已完成之補丁硬化能力投入小流量實戰驗證。透過受控 Canary 與數據驅動的失敗桶收斂，證明 Patch Hardening 確實能提升修復效率與穩定性。

## 📅 實作路線圖 (2026-06-02 ~ 2026-06-30)

### Milestone 1: Canary 契約化 (Contracting)
- [ ] **T5.1**: 固化 `PHASE_5_CANARY_EXECUTION_CHECKLIST`，明確准入與退出條件。
- [ ] **T5.2**: 標配 Canary Receipt Schema，包含 `expected_stop_layer`, `syntax_gate_passed` 等核心遙測。
- [ ] **T5.3**: 建立 Phase 5 Baseline Pack（以 5-probe matrix 為對照基線）。

### Milestone 2: 小流量實戰 (Small-Scale Execution)
- [ ] **T5.4**: 執行第一輪小流量 Canary（固定 strata 樣本池）。
- [ ] **T5.5**: 產出 JSON Summary + CSV Detail 審計報表。

### Milestone 3: 失敗桶收斂 (Convergence)
- [ ] **T5.6**: 針對高頻失敗桶（如 `SEARCH_MISMATCH`）執行定向修補實驗。
- [ ] **T5.7**: 執行第二輪 Canary，驗證改善的可重現性。
- [ ] **T5.8**: 產出最終 Closeout Verdict (HOLD / EXPAND / REVERT)。

---

## 📈 成功標準 (Acceptance Criteria)
1. **出口一致性**: Stop-layer 一致性不低於 Phase 4 基線。
2. **數據驅動**: 失敗桶分佈可精確比較，不接受純敘事解讀。
3. **治理完整**: 所有 Canary 執行均具備完整的證據封存 (Evidence Seal) 與收據。

[NEXUS STATUS: PHASE 5 CANARY INITIATED]

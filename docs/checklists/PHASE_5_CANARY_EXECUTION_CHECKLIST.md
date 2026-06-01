# 🛡️ PHASE 5: Canary Execution Checklist

## 🟢 1. 准入條件 (Admission Criteria)
- [x] **Step 5 Sealed**: Orchestration 與 Phase 解耦已完成並通過 18 組核心測試。
- [x] **Step 6 Validated**: B1/C2/D1 探針對齊率達 100%。
- [x] **Milestone 1 Artifacts**: `Syntax Preflight` 與 `Refusal Recovery` 邏輯已就緒。
- [x] **Baseline Ready**: Phase 4 的 5-probe 審計數據已封存。

## 🧪 2. 執行程序 (Execution Runbook)
- [ ] **Step 1**: 選擇固定樣本池（strata 覆蓋：Auth, Semantic, Patcher, Env）。
- [ ] **Step 2**: 確保 `validate_syntax_gate=True`。
- [ ] **Step 3**: 執行 Canary Run 並監控 `stop_layer` 是否偏移。
- [ ] **Step 4**: 收集 `diagnostics` 與 `wall_time` 數據。

## 🔴 3. 退出與回滾條件 (Exit & Rollback)
- **立即回滾**:
    - 出現 `expected_stop_layer` 異常位移（例如：應在 patcher 停卻進到 verification 且失敗原因不明）。
    - 新增遙測導致 `CapabilityReceipt` 解析崩潰。
- **停止擴樣**:
    - `SYNTAX_ERROR` 攔截後更正成功率低於 20%。
    - 14B 模型連續出現 3 次 `MODEL_REFUSAL` 且 Recovery 指令失效。

## 🏁 4. 結案判定 (Closeout Verdicts)
- **HOLD_OBSERVATION_ONLY**: 證據不足，或審計純淨度有疑慮。
- **CANARY_EXPAND_APPROVED**: 小流量表現穩定，允許擴大測試樣本。
- **REVERT_AND_RCA**: 發現架構性退化，立即回退代碼並執行根因分析。

---
**NEXUS IDENTITY: 384c6fd02 + v2.9 RUNTIME-ALIGNED**

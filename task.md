# 🛡️ LocalHeal Surgical Plan: Precision Battlesuit Refactoring

## 🎯 核心目標
消除 `SEARCH_MISMATCH` 的跨函數漂移，將 LocalHeal 從「直覺修補」升級為「高精度代數戰甲」，並完成 Phase 3 數據合約與治理審計對接。

## 📅 實作路線圖 (2026-05-31 ~ 2026-06-04)

### Phase 0: 基礎設施與回歸基準 (Infrastructure & Base Tests)
- [x] **T0-1**: 補齊 `nexus/services/local_heal/interface.py` 或修復測試導入路徑。
- [x] **T0-2**: 建立最小 Smoke Tests 覆蓋：`patcher`, `corrector`, `matcher`, `pipeline`。
- [x] **T0-3**: 將 `astropy-13033` 失敗樣本固化為 Regression Fixture。

### Phase 1: Matcher 漂移杜絕 (Anti-Drift Matcher)
- [x] **T1-1**: 限制 `closest_match` 檢索順序：已定位檔案 > 已定位函數 > 已定位 Span。
- [x] **T1-2**: 引入語義與結構權重：同函數、同 Exception Type、同縮排優先。
- [x] **T1-3**: 衝突處理：多候選高度接近時強制 RETURN/Fail-closed，禁止盲選。
- [x] **T1-4**: 對 `ValueError`/`TypeError` 等關鍵語義標籤設置漂移懲罰 (Hard Penalty)。

### Phase 2: HUD Retry 契約強化 (HUD Feedback Upgrade)
- [x] **T2-1**: 升級 HUD 文案，區分 `canonical_snippet` 與 `fallback_snippet`。
- [x] **T2-2**: 若存在安全候選，重試 Prompt 只提供該 Span 的 Canonical 原文。
- [x] **T2-3**: 強制模型契約：要求 SEARCH 區塊必須 literal copy，嚴禁改寫語義。
- [x] **T2-4**: 實作二輪重試的 `Span-anchored Copy Mode`。

### Phase 3: Bounded Auto-Correction 收斂 (Safe Compensation)
- [x] **T3-1**: 限制 Auto-correct 觸發條件：必須滿足「單一高相似候選 + 明確 resolved_span + 結構一致」。
- [x] **T3-2**: 提高相似度閾值 (Similarity Threshold) 並禁止跨塊/跨函數補償。
- [x] **T3-3**: 在 `is_auto_corrected=True` 時強制記錄匹配原文與 Span 證據。

### Phase 4: Phase 3 數據合約對位 (Algebraic Contract Alignment)
- [x] **T4-1**: Planning 階段正式對接 `NexusDiagnosis` (填寫 `reasoning_mode`, `violated_invariants`)。
- [x] **T4-2**: Repair 階段對接 `NexusRepair` (填寫 `rewrite_trace`, `risk_delta`)。
- [x] **T4-3**: 根據問題難度自動升級 `reasoning_mode` 為 `ALGEBRAIC` (針對 astropy 等數學語義題)。

### Phase 5: 治理收口與證據密封 (Governance & Sealing)
- [x] **T5-1**: LocalHeal Adapter 標準化輸出：`selected`, `invoked`, `evidence_present`, `gate_passed`, `evidence_refs`, `telemetries`。
- [x] **T5-2**: 對接 `evidence_barrier`，確保無證據、無密封的產物無法過 Gate。

---

## 📈 成功標準 (Acceptance Criteria)
1. **漂移消除**: `astropy-13033` 的 Mismatch Feedback 不再跳向不相關的 `TypeError` 片段。 (Verified 🟢)
2. **治理合規**: 每次成功 Run 必須產出含 `evidence_refs` 與 `telemetries` 的 `CapabilityReceipt`。 (Infrastructure Ready 🟢)
3. **可歸因性**: 失敗日誌能明確分辨是 Matcher 漂移、Patcher Guard 拒絕、模型推理錯、還是 Verification 擋下。 (Verified 🟢)

[NEXUS STATUS: Phase 0-5 COMPLETED]

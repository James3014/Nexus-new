# 🦀 Nexus Rust Migration: Wave 2 Task List

> **Status**: IN-PROGRESS
> **Latest Commit SHA**: 4d86cc9ca
> **Nexus Identity**: 4d86cc9ca + v3.5.0 RUNTIME-ALIGNED
> **Strategy**: Dual-run Compare -> Shadow Verification -> Primary Cutover

---

## 🏗️ Wave 2 里程碑與任務

### 🚩 Milestone R2-A: Baseline Replay Engine (回放引擎)
- [ ] **TR2.1**: 實裝 `ReplayContract` Rust 結構與驗證器。
- [ ] **TR2.2**: 建立 `nexus-core-rs/src/replay.rs`，處理確定性的回放執行檢查。
- [ ] **TR2.3**: 建立 Python vs Rust 回放一致性測試集。

### 🚩 Milestone R2-B: Vertical Slice Planner (垂直切)
- [ ] **TR2.4**: 將 `VerticalSlicePlanner` 核心邏輯移入 Rust，實裝 `HORIZONTAL_SLICE_DETECTED` 攔截器。
- [ ] **TR2.5**: 定義 `slice_receipt.v1` Rust 輸出格式。
- [ ] **TR2.6**: 驗證增量實作契約（UI/API/Service/Data）在 Rust 中能正確識別。

### 🚩 Milestone R2-C: Contamination Guard (污染檢查)
- [ ] **TR2.7**: 將正則表達式為主的 `ContaminationGuard` 核心下沉至 Rust 以提升效能。
- [ ] **TR2.8**: 定義 `design_leakage` 失敗桶，產出 `research_receipt` 內的污染指標。

---

## 📈 驗收與回退 (Acceptance & Rollback)
1. **驗收點**: 每個模組必須通過 100 筆以上真實/模擬數據的 `Dual-run Compare`，無 Mismatch。
2. **性能點**: 預計 `ContaminationGuard` 與 `SlicePlanner` 的處理延遲下降 > 30%。
3. **回退點**: 若 Rust IPC 出現 Timeout 或 Mismatch，立即切回 Python 舊路徑。

[NEXUS STATUS: RUST WAVE 2 INITIATED]

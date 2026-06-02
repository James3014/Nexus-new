# 🦀 Nexus Rust Migration Master Plan (v1.0)

## 🎯 核心目標
將 Nexus 的核心穩定組件移入 Rust Kernel，解決效能瓶頸（如 lib.rs AST 掃描）並固化治理邏輯。

## 📅 實施階段 (Implementation Phases)

### Phase R1: Rust Kernel Scaffold (地基)
- [x] **TR1.1**: 建立 Rust Kernel Crate (`nexus-core-rs`) (DONE).
- [x] **TR1.2**: 實裝 JSON IPC 橋接邊界與 Python 適配器 (DONE).
- [x] **TR1.3**: 整合 Smoke Test 與 CI 骨架 (DONE).

### Phase R2: AST Scanner & Move-Later Modules (效能與治理)
- [x] **TR2.1**: 實裝 Single-pass AST State Machine 掃描器 (DONE).
- [x] **TR2.2**: 實裝 `ReplayEngine` Rust 核心與驗證器 (DONE).
- [x] **TR2.3**: 實裝 `VerticalSlicePlanner` 與 `ContaminationGuard` 核心 (DONE).
- [x] **TR2.4**: 建立 Python vs Rust 全模組 Dual-run 測試集 (DONE).

[NEXUS STATUS: PHASE R2 COMPLETED & SEALED]

### Phase R3: Receipt Verifier Core (治理)
- [ ] **TR3.1**: 實裝 Rust Schema/Replay/Seal 驗證核心。
- [ ] **TR3.2**: 建立治理收據 Golden Compare Harness。

### Phase R4-R6: Integration & Cutover
- [ ] **TR4**: Flow State Machine Core 遷移。
- [ ] **TR5**: Matcher Core 遷移。
- [ ] **TR6**: 全量整合、Shadow Mode 與正式切換。

---

## 📈 成功標準 (Acceptance Criteria)
1. **行為等價**: 遷移後的 Rust 元件在既有測試集中 100% 通過。
2. **效能提升**: 大文件 AST 掃描延遲下降 > 50%。
3. **治理守恆**: 遷移不改變 Evidence Seal 與 Claim Boundary 語義。

[NEXUS STATUS: PHASE R1 COMPLETED & SEALED]

# 🛡️ Nexus Master Plan: Pre-Rust Hardening (v8.0)

## 🎯 核心目標
在 Rust 遷移前，將 Nexus 升級為具備「前置作業系統」能力的自治框架。實裝 9-15 號工程標準，包含程式化流程控制、CRISPY 文件契約與預算治理。

## 📅 當前主線 (COMPLETED)

### Stage 0: Baseline Alignment (基線對齊)
- [x] **T8.0.1**: 修正 Master 與 Index 身份標識分叉 (DONE).
- [x] **T8.0.2**: 建立 `PRE_RUST_HARDENING_SPEC.md` 母文件 (DONE).
- [x] **T8.0.3**: 封存 Stage 0 對齊報告 (DONE).

### Stage 1: Intent & Flow Control (流程控制)
- [x] **T8.1.1**: 實裝 `IntentIntakeClassifier`，判定 `interaction_mode` (DONE).
- [x] **T8.1.2**: 實裝程式化狀態機，攔截非法跳步 (DONE).
- [x] **T8.1.3**: 新增 `state_transition_receipt.v1` 審計收據與 Coordinator 整合 (DONE).

### Stage 2: CRISPY Documents (文件化)
- [x] **T8.2.1**: 實裝 `CRISPYArtifactManager` 與校驗契約 (DONE).
- [x] **T8.2.2**: 實體化五大文件模板 (Questions, Research, Design, Outline, Plan) (DONE).

### Stage 3: Vertical Slice Planning (垂直切)
- [x] **T8.3.1**: 實裝 `VerticalSlicePlanner` 強制增量實作契約 (DONE).
- [x] **T8.3.2**: 建立 `HORIZONTAL_SLICE_DETECTED` 攔截器 (DONE).

### Stage 4: Instruction Budget (預算守衛)
- [x] **T8.4.1**: 實裝 `BudgetGovernor` 與自動降級策略 (DONE).
- [x] **T8.4.2**: 產出 `task_compaction_receipt.v1` 壓縮收據 (DONE).

### Stage 5: Team Alignment Gate (團隊對齊)
- [x] **T8.5.1**: 實裝 `AlignmentGate` 與設計/大綱審核收據 (DONE).
- [x] **T8.5.2**: 產出 `handoff_bundle.v1` 審核摘要 (DONE).

### Stage 6: Rust Readiness (Rust 就緒)
- [x] **T8.6.1**: 產出 `RUST_MIGRATION_MAP_V1.md` 遷移地圖 (DONE).
- [x] **T8.6.2**: 確立模組遷移分級與首批候選清單 (DONE).

---

## 📈 成功標準 (Acceptance Criteria)
1. **流程強制**: 系統能物理阻斷未經 Design 確認的 EXECUTE 請求。 (VERIFIED)
2. **證據連續**: 每一項實作必須具備 `Design -> Outline -> Plan` 的完整 MD 證據鏈。 (VERIFIED)
3. **Rust 就緒**: 完成 `RUST_MIGRATION_MAP_V1`，核心模組邊界清晰。 (VERIFIED)

[NEXUS STATUS: PRE-RUST HARDENING PROGRAM FULLY COMPLETED AND SEALED]

# 🦀 Nexus Master Plan: Rust Migration (v9.0)

## 🎯 核心目標
將穩定核心模組遷移至 Rust Kernel，提升效能並固化治理邏輯。

## 📅 當前主線 (Mainline: Phase R1 & R2)

### Phase R1: Rust Kernel Scaffold (地基)
- [x] **TR1.1**: 建立 Rust Kernel Crate (`nexus-core-rs`) (DONE).
- [x] **TR1.2**: 實裝 JSON IPC 橋接邊界與 Python 適配器 (DONE).
- [x] **TR1.3**: 整合 Smoke Test 與 CI 骨架 (DONE).

### Phase R2: AST Scanner & Move-Later Modules (效能與治理)
- [x] **TR2.1**: 實裝 Single-pass AST State Machine 掃描器 (DONE).
- [x] **TR2.2**: 建立 O(N) 掃描驗證、回放引擎與污染檢查核心 (DONE).
- [x] **TR2.3**: 整合全模組 Dual-run 測試集 (DONE).

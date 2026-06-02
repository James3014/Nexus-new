# 🛡️ Nexus Master Plan: Pre-Rust Hardening (v8.0)

## 🎯 核心目標
在 Rust 遷移前，將 Nexus 升級為具備「前置作業系統」能力的自治框架。實裝 9-15 號工程標準，包含程式化流程控制、CRISPY 文件契約與預算治理。

## 📅 當前主線 (Mainline: Stage 0 & 1)

### Stage 0: Baseline Alignment (基線對齊)
- [ ] **T8.0.1**: 修正 Master 與 Index 身份標識分叉 (`v3.1.0` vs `v3.1.1`)。
- [ ] **T8.0.2**: 建立 `PRE_RUST_HARDENING_SPEC.md` 母文件。
- [ ] **T8.0.3**: 封存 Stage 0 對齊報告。

### Stage 1: Intent & Flow Control (流程控制)
- [x] **T8.1.1**: 實裝 `IntentIntakeClassifier`，判定 `interaction_mode` (DONE).
- [x] **T8.1.2**: 實裝程式化狀態機，攔截非法跳步 (DONE).
- [x] **T8.1.3**: 新增 `state_transition_receipt.v1` 審計收據與 Coordinator 整合 (DONE).

### Stage 2-5: CRISPY & Budget (預告)
- [ ] **T8.2**: CRISPY 五文件產物實體化 (NEXT: Questions, Research, Design, Outline, Plan).
- [ ] **T8.3**: 垂直切規劃器 (Vertical Slice Planner) 實裝。
- [ ] **T8.4**: 指令預算守衛 (Budget Governor) 實裝。

---

## 📈 成功標準 (Acceptance Criteria)
1. **流程強制**: 系統能物理阻斷未經 Design 確認的 EXECUTE 請求。
2. **證據連續**: 每一項實作必須具備 `Design -> Outline -> Plan` 的完整 MD 證據鏈。
3. **Rust 就緒**: 完成 `RUST_MIGRATION_MAP_V1`，核心模組邊界清晰。

[NEXUS STATUS: PRE-RUST HARDENING PROGRAM INITIATED]


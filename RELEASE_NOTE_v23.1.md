# Nexus Release Note v23.1.0-SOTA

**Release Date**: 2026-04-05
**Governance Version**: v23.1.0-Hardened
**Codename**: Eternal Neural Swarm (Governance Upgrade)

---

## 💎 Release Overview | 發佈概覽

Nexus v23.1 引入了全新的 **19 層治理架構 (19-Layer Governance Archetecture)**。這次升級的核心目標是在不破壞 PXDRAC 契約的前提下，實現治理規則的輕量化注入與跨回合狀態的物理級繼承。

## 🚀 Key Improvements | 關鍵改進

### 1. 19 層治理摘要化 (L0/L1 Context Injection)
- **L0治理根**: 摘要化授權邊界 (Boundaries) 與禁止行為 (Prohibited Actions)，實現治理規則常駐且低佔用。
- **L1任務索引**: 將當前任務 ID、相位與狀態權杖 (State Token) 轉化為 Prompt 治理指針。

### 2. Audit-to-Crystallize Handoff (狀態握手)
- 實作 `.nexus/state/last_handoff.json` 工件，於 A 與 C 相位間完成狀態封存。
- 支援下一回合任務自動識別與讀取 (Read-back Loop Closed)。

### 3. Context 減量優化引擎 (-30%)
- 透過動態分配與壓縮 L2-L19 層級，達成至少 30% 的 Context 預算節省。
- 保證 L0/L1 核心治理層不被削減。

### 4. 證據鏈與合約對位 (Manifest Integration)
- 將 Handoff 工件正式連結至 `manifest.json` 與 artifact chain。
- 失敗路徑完全對接 `NexusExitCode` 狀態機。

---

## 🛡️ Release Verification | 發佈驗收

- [x] **Night Shift 演化收斂**: Score 8.5 (PASS)
- [x] **兩回合循環測試**: 狀態讀取成功 (PASS)
- [x] **引擎規格對位**: MUSE SPEC v23.1 更新 (PASS)

**Status**: **v23.1 Governance Aligned with PXDRAC Contract & Resident State Active.**

---
*Signed by Nexus Battlegear Engineer*

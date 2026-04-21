# 🔐 Access Control & Tactical Firewall
**[PHYSICAL_STATUS: MATRIX_ENFORCED | TACTICAL_AWARE]**

## 1. 領地防禦與訪問控制
Nexus 使用 `DomainFirewall` 與 `CapabilityGate` 實施多維度的工具權限管理：
- **領地防禦 (Domain-Level)**: 根據實體物理路徑區分權限。
- **階段隔離 (Phase-Level)**: 根據 P-X-D-R-A-C 生命週期動態授權工具。

## ⚙️ 實體化防禦規約
- **階段工具隔離 (CapabilityGate)**: 
    - **Plan**: 僅限讀取工具。
    - **Repair**: 授權編輯與補丁工具。
    - **Audit**: 僅限測試與校驗工具。
    - **Crystallize**: 授權 Commit 與記憶寫入。
- **推理模式強制 (Reasoning Policy)**: 
    - **ALGEBRAIC**: 必須具備邏輯證明（核心區強制）。
- **誠信守護 (ACL)**:
    - **黑名單**: 物理阻斷包含 `rm -rf /` 或 `kill -9` 的 Shell 指令。

## 2. 物理實體 (Today's Decoupled Alignment)
- **Governance Shield**: `nexus/governance/capability_gate.py`。
- **Firewall Facade**: `nexus/core/capability_gate.py` (外觀入口)。
- **Enforcement**: `managed_toolsets(phase)` 物理過濾 Agent 可見工具。

---
**[Source: Refactor Cycle April 21, 2026 | SEALED]**

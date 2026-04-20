# 🔐 Access Control & Tactical Firewall
**[PHYSICAL_STATUS: MATRIX_ENFORCED | TACTICAL_AWARE]**

## 1. 領地防禦與訪問控制
Nexus 使用 `DomainFirewall` 與 `ACL` 實施細粒度的工具訪問控制，並約束 Agent 的「推理心態」。

## ⚙️ 實體化防禦規約
- **領地分類 (Tactical Map)**: 
    - **Q1_Critical_Core**: 嚴禁直覺生成，必須通過 1-bit Core 驗收。
    - **Q2_Research_Lab**: 允許高增量實驗，具備回滾寬限期。
- **推理模式強制 (Reasoning Policy)**: 
    - **INTUITIVE**: 允許模糊匹配。
    - **ALGEBRAIC**: 必須具備邏輯證明（核心區強制）。
- **誠信守護 (ACL)**:
    - **黑名單**: 物理阻斷包含 `rm -rf /` 或 `kill -9` 的 Shell 指令。
    - **保護埠**: 嚴禁訪問敏感數據庫埠 (5432, 27017)。

## 2. 物理實體
- **Firewall**: `nexus/core/domain_firewall.py`。
- **SSoT**: `nexus/config/tactical_map.json`。
- **Enforcement**: `authorize(skill_id, current_domain)` 物理阻斷非領地技能。

---
**[Source: New Dimension Audit Batch A - 2026-04-20]**

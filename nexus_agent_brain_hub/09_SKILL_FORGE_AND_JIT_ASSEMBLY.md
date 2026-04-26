# ⚒️ Skill Forge & JIT Assembly
**[PHYSICAL_STATUS: JIT_COMPILED | AST_SAFE]**

## 1. 技能自動化組裝 (Self-Assembly)
當 Nexus 偵測到現有技能集無法覆蓋當前意圖時，啟動 `SkillAssembler` 現場鍛造新技能。

## ⚙️ 實體化鍛造規約
- **自動生成 (Assemble)**: 自動產出帶有 YAML Metadata 與 `Soul Trinity Mapping` 的 `SKILL.md`。
- **JIT 驗證 (Just-In-Time)**: 
    - **AST Scan**: 載入前強制掃描語法樹，阻斷注入攻擊。
    - **Sandbox Smoke**: 隔離環境煙霧測試。
- **靈魂映射**: 新技能自動繼承 `MUSE_PROTO` 全域約束。

## 2. 技術特性
- **JIT Loading**: 僅在需要時編譯並注入內存。
- **Weight Learning**: 根據歷史成功率動態調整調度權重。

## 3. 物理實體
- **Assembler**: `nexus/core/skill_assembler.py`。
- **路徑**: `skills/` 子目錄。

---
**[Source: New Dimension Audit Batch C - 2026-04-20]**

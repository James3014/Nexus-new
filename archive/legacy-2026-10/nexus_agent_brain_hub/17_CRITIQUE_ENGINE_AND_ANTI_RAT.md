# 🛡️ Critique Engine & Anti-Rationalization
**[PHYSICAL_STATUS: BEHAVIORAL_ENFORCED | ANTI_SLOP]**

## 1. 代碼美學與行為誠信
Nexus 透過 `CritiqueEngine` 強制執行「禁止合理化」規約，確保 Agent 不會為了結案而規避測試。

## ⚙️ 實體化審核規約
- **計畫預審 (Prescan)**: 
    - **攔截關鍵字**: `skip tests`, `manual check`, `todo`, `暫不測試`。
    - **動作**: 只要計畫中出現上述字眼，立即拋出 `RationalizationError` 並阻斷執行。
- **過度宣稱攔截**: 若回覆包含 `solved`, `fixed` 但 `evidence_bundle` 信心度不足，強制阻斷。
- **反事實檢索**: 在 `final_review` 時自動搜尋 `known-failures` 知識庫，尋找修復路徑的負面證據。

## 2. 物理門檻
- **Aesthetic Score**: 必須 >= 90。
- **TDD 鐵律**: 嚴禁規避測試，必須先寫 RED 測試並立即修復。

---
**[Source: New Dimension Audit Batch B - 2026-04-20]**

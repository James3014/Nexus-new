# 🏛️ Compliance & Truth Claims

## 1. 合規性與真值管理
Nexus 需要在高度監管的環境中運行，因此必須確保每一條知識 (Knowledge) 都是真實且可審計的。

## 2. 真值斷言寄存器 (Truth Claims Register)
- **定義**: 存放在 Wiki 中的「真值條目」，標註了系統已驗證的特性或已知限制。
- **保護等級**: 只有通過 `Red-Team Audit` 的內容才能被標註為 `HIGH_CONFIDENCE`。

## 3. 譜系追蹤 (Knowledge Lineage)
- Nexus 紀錄每一條知識的來源（如：文件 URL、Git Commit、測試 Log）。
- 如果源頭發生漂移（如：程式碼被改動），關聯的真值斷言會自動降權為 `STALE`。

## 4. 指令執行策略 (Command Policy)
- **白名單機制**: `scripts/ops/wiki_truth_claims_check.py` 監控所有的系統指令，防止 Agent 在 Wiki 頁面中嵌入惡意或未授權的代碼。
- **審核路徑**: 任何對系統核心策略的變更，必須同步更新 `Current_Compliance_Status.md`。

---
**[Source: nexus_wiki_vault/06_Ops/Ops - Truth Claims Register.md]**

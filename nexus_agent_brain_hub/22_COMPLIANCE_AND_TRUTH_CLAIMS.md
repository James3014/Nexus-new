# 🏛️ Compliance & Truth Claims
**[PHYSICAL_STATUS: RED_TEAM_AUDITED | LINEAGE_PROTECTED]**

## 1. 合規性與真值管理
Nexus 在受控環境中運行，必須確保每一條知識均真實且可審計。

## ⚙️ 實體化真值規約
- **真值寄存器 (Truth Claims Register)**: 
    - 存放於 Wiki 中的「真值條目」。
    - **HIGH_CONFIDENCE**: 只有通過紅隊審計的斷言才能獲得此標籤。
- **譜系追蹤 (Knowledge Lineage)**: 
    - 紀錄每一條知識的來源（URL, Commit, Test Log）。
    - 原始碼變更會自動將相關斷言降權為 `STALE`。
- **指令執行策略 (Command Policy)**: 
    - **白名單**: `wiki_truth_claims_check.py` 監控 Wiki 內的指令，防止惡意注入。
- **紅隊硬化**: 
    - 自動化紅隊調用證據必須附加於 `hallucination_evidence.json`。

## 2. 合規標籤
- **v25.7 Ultra-Hardened**: 目前的穩定基準線版本。

---
**[Source: New Dimension Audit Batch E - 2026-04-20]**

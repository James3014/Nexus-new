# 🧠 Learning Closure Matrix & Lessons

## 1. 錯誤歸因與防再發矩陣
Nexus 的核心治理原則是「發生一次，就學會一次」。所有失敗必須轉化為可執行的規則。

## 2. 關鍵教訓分類 (Error-to-Prevention)

| Error Type | Prevention Rule | Effective Date |
|---|---|---|
| **Nested Test Skip** | 強制頂層函數定義，驗證 pytest 收集數量。 | 2026-04-17 |
| **Contract SHA Drift** | 結算前強制執行 `rev-parse HEAD` 與合約對位。 | 2026-04-17 |
| **Relative Import Fail** | 腳本入口一律採用絕對匯入 `from nexus.x...`。 | 2026-04-17 |
| **Quota Deadlock** | 審計前檢查 Token 配額，不足時強制進入 STALLED。 | 2026-04-18 |
| **Code16 Deadloop** | 物理完整性與語義驗收解耦。 | 2026-04-19 |

## 3. 回寫規約 (Writeback Protocol)
當任務失敗或退件時，Agent 必須：
1.  **歸因**: 找出 Root Cause。
2.  **提案**: 提出一條新的 Prevention Rule。
3.  **實體化**: 將教訓寫入 `.nexus/reports/lesson_writeback.json` 並同步至 Wiki。

## 4. 閉環指標
- **MTTR (Mean Time To Recover)**: 從故障到修復的平均時間。
- **Repeat Rate**: 同一類錯誤在 30 天內的重覆發生率（目標為 0%）。

---
**[Source: nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md]**

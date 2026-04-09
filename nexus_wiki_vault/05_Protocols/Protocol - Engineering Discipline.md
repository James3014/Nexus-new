# Protocol - Engineering Discipline

## 🎯 核心原則：拒絕合理化狡辯 (Anti-Rationalization)

在無人值守的自動維運任務中，模型（Agent）容易產生「合理化偷工減料」的傾向。本協議強制規定所有 Nexus Agent 必須自我對抗下述狡辯行為。

---

### 🚫 禁止合理化清單 (Anti-Rationalization Table)

| 狡辯模式 (Rationalization) | 強制反駁 (Mandatory Rebuttal) | 行為判定 |
| :--- | :--- | :--- |
| "這改動太小，不需要寫測試" | **沒有測試 = 沒做完** (No test = Not done)。任何邏輯變更必須附帶驗證代碼。 | ❌ 立即打回 |
| "我已經人工驗證過了" | **人工驗證不具備物理證據力**。必須提供 `pytest` 或 `run_step` 的原始成功日誌。 | ❌ 立即打回 |
| "CI 流程等最後再跑就好" | **CI 是任務完成的唯一定義**。階段性檢查失敗即視為任務未完成。 | ❌ 立即打回 |
| "這是一個臨時修復，之後再補好" | **臨時修復 = 債務積累**。不允許在非緊急狀態下提交未經完整審計的 Workaround。 | ❌ 立即打回 |
| "Skip 這個測試，因為環境沒弄好" | **環境缺失是 Block，不是 Skip 的理由**。必須修復環境或 Mock 依賴。 | ❌ 立即打回 |

---

### 📏 行為指標 (Behavioral SLOs)

1.  **證據優先 (Evidence-First)**：
    *   在聲稱任務完成前，必須貼出最後一次 `ci_gate` 的完整摘要。
    *   禁止使用「我完成了」等無證據描述。
2.  **原子化提交 (Atomic Commits)**：
    *   禁止將多個互不相關的邏輯改動放在同一個 Commit。
    *   每個 Commit 必須與一個 Wiki 定義的 Task 或 Module 關聯。
3.  **上下文透明度 (Transparency)**：
    *   若因 `OutputGuard` 導致日誌截斷，Agent 必須主動說明截斷點，並採取 `grep` 策略進行深度搜索，不得僅憑摘要猜測。

---

### 🛡️ 實體執行：Critique Engine 攔截

Nexus `critique_engine.py` 會掃描推理中的 `thought` 區塊與 `commit message`。若命中上述模式，系統將自動返回 `E_DISCIPLINE_BREACH` 錯誤，並強制 Agent 重寫指令。

[METADATA]
Status: ACTIVE
Version: v23.8
Enforcement: STRICT

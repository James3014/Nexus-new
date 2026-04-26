# 🧠 Hallucination Guard & Acceptance Check
**[PHYSICAL_STATUS: ALGORITHMIC_CONSCIENCE | HARD_TRUNCATION]**

## 1. 證據驅動驗收 (Acceptance-First)
Nexus 不接受無物理證據的完成宣告。`HallucinationGuard` 對所有證據包進行權重審計。

## ⚙️ 實體化計分規約
- **判定門檻**: **REJECTED (>= 6分)** 將強制阻斷任務結案。
- **關鍵觸發項**:
    - **Evidence Gap (7分)**: 宣稱修復但無 Code 或 Log 證據。
    - **Benchmark Failure (9分)**: **[FORCE_REJECTED]** 成功率低於門檻。
- **自動結晶**: 任務通過後，自動調用 `crystallize_lessons.py` 將教訓轉化為長期信念。

## 2. 證據管理
- **Truncation**: 系統自動執行 `truncate_output`，在保留關鍵失敗特徵的同時節省 Token。
- **Evidence Schema**: 強制要求 `code_artifacts`, `test_artifacts` 與 `command_artifacts`。

---
**[Source: Truth Realignment Audit Stage 6 - 2026-04-20]**

# 📖 System Overview & Glossary
**[PHYSICAL_STATUS: TERMINOLOGY_SSOT | LAYER_1_FOUNDATION]**

## 1. 定義 (Definition)
Nexus 是一個治理型 Agent 作業系統，旨在透過物理規約將 LLM 的不確定性轉換為生產穩定性。

## 2. 術語表 (Glossary)
- **AAAK**: 30x 語義提煉方言。
- **1-bit Core**: 原子化決策判決核心。
- **HI**: 幻覺指數。
- **Drift**: 真值偏離度。

## 3. 🛑 核心錯誤碼 (Errors Enum)
| Code | Label | Semantics |
|---|---|---|
| **0** | SUCCESS | 任務完成，證據鏈完整。 |
| **1** | FAILED | 修復失敗，無須升級。 |
| **2** | ESCALATED | 需要重新規劃。 |
| **3** | HUMAN_REVIEW | 嚴重治理違規，人工介入。 |

---
**[Source: nexus/core/exit_codes.py]**

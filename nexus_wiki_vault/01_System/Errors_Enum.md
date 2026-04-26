---
aliases: '[Terminal States, Exit Codes, Critical Errors]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
source_of_truth: nexus/core/exit_codes.py
status: hardened
tags: '[system, errors, enum, ssot]'
title: System - Errors Enum
---

# System - Errors Enum (v1.0)

## One-sentence summary
本頁集中枚舉 Nexus 系統中具備「阻斷語義」的核心錯誤碼與狀態常量。

## 🛡️ 核心退出碼 (IntEnum)
詳見：[[Exit_Code_Registry]]。
- `SUCCESS = 0`
- `FAILED = 1`
- `ESCALATED = 2`
- `HUMAN_REVIEW = 3`

## 🛑 治理關鍵錯誤 (Governance Errors)

| Error Class | Severity | Description |
| :--- | :--- | :--- |
| **`Code 16`** | 🔴 P0 | **Deadlock**: 物理完整性與語義驗收發生死鎖。 |
| **`Drift P0`** | 🔴 P0 | **Semantic Drift**: 代碼變更超出 Wiki 描述範圍。 |
| **`HI 6+`** | 🔴 P0 | **Hallucination**: 指數超標，證據不足或數據造假。 |
| **`AestheticViolation`** | 🟡 P1 | **Quality**: 代碼美學評分低於 90。 |
| **`BudgetExceeded`** | 🟡 P1 | **Thrift**: 任務 Token 消耗超過預設配額。 |

---
**[Source: nexus/core/exit_codes.py]**

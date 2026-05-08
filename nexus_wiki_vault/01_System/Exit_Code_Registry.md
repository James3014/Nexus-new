---
aliases: '[Exit Codes, Terminal Semantics, Process Results]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
source_of_truth: nexus/core/exit_codes.py
status: hardened
tags: '[system, exit_codes, governance, ssot]'
title: System - Exit Code Registry
---

# System - Exit Code Registry (v1.0 SSOT)

## One-sentence summary
本頁為 Nexus 系統所有進程退出語義的 **唯一真值來源 (SSOT)**，定義了成功、失敗、升級與人工介入的物理判定標準。

## 📊 Canonical Exit Codes (標準對照表)

| Code | Label (標籤) | Semantics (語義) | CI Blocking | Handoff Trigger |
| :--- | :--- | :--- | :--- | :--- |
| **0** | `SUCCESS` | 所有階段通過，證據鏈完整。 | 🟢 NO (GREEN) | NO |
| **1** | `FAILED` | 修復失敗且無須人工介入。 | 🔴 YES (RED) | NO |
| **2** | `ESCALATED` | 指揮官必須重新規劃；不可恢復。| 🔴 YES (RED) | NO |
| **3** | `HUMAN_REVIEW`| 違反治理規約，必須由人工覆核。 | 🔴 YES (RED) | ✅ YES |

## 🛡️ 治理政策 (Governance Policy)

### 1. CI 阻斷政策
- **原則**: 只有 Code `0` 會被 CI Gate 視為「綠燈」。
- **動作**: 任何非零返回碼均會中止 `Promotion` 管線。

### 2. 人機移交政策 (Handoff)
- **觸發**: 當返回碼為 `3 (HUMAN_REVIEW)` 時，系統強制執行 `HandoffBundle` 寫入。
- **後果**: 外部調用者（如 GitHub Action）應解析此碼並發送緊急通知。

### 3. 重試政策 (Retry)
- **自動重試**: 僅適用於特定網路抖動引發的 `FAILED (1)`。
- **禁止重試**: 對於 `HUMAN_REVIEW (3)` 與 `ESCALATED (2)` 嚴禁自動重試，防止無窮遞迴。

---
**[Source: nexus/core/exit_codes.py]**

## Role / responsibility
- 提供單一定義與門禁行為準則，讓運行時與 CI 對退出語義保持一致。

## Upstream
- [[01_System/Errors_Enum|Errors Enum]]
- [[06_Ops/Ops - Acceptance and Release|Acceptance and Release]]

## Downstream
- [[06_Ops/Ops - Closeout Hard Gate|Closeout Hard Gate]]
- [[07_Compliance/Governance - Capability Gate and Tool Isolation|Capability Gate and Tool Isolation]]

## Related modules / files
- [Source: nexus/core/exit_codes.py]
- [Source: scripts/engine/nexus_cli.py]
- [[System Overview]]

## Source notes
- [Source: compiled-wiki]

## Open questions / conflicts
- 是否需要將 `ESCALATED` 分離為可恢復與不可恢復兩層以降低運維成本？

---
aliases: '[Evidence Schema, Hallucination Payload]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
source_of_truth: nexus/core/hallucination_guard.py
status: hardened
tags: '[ops, audit, evidence, json]'
title: Ops - Evidence Bundle Format
---

# Ops - Evidence Bundle Format (v1.0 Specification)

## One-sentence summary
本文件定義 `hallucination_evidence.json` 的標準物理結構，這是通過 `HallucinationGuard` 審計的唯一合法數據載體。

## ⚙️ 實體結構 (JSON Schema)

```json
{
  "final_response": "Agent的最終回覆全文",
  "evidence_bundle": {
    "code_artifacts": ["實際修改的檔案路徑1", "..."],
    "test_artifacts": ["測試指令及其輸出摘要"],
    "command_artifacts": ["關鍵Bash指令與return_code"],
    "log_artifacts": ["相關日誌節點ID"],
    "aggregates": {
      "success_rate": 1.0,
      "success_threshold": 0.8,
      "repair_mode": "V25-ALIGNED"
    }
  }
}
```

## 🛡️ 填充規約
1. **Truncation**: `test_artifacts` 中的日誌若超過 2000 行，必須強制執行首尾截斷。
2. **Absolute Paths**: `code_artifacts` 必須使用專案根目錄起的相對路徑。
3. **Implicit Success**: 嚴禁在 `aggregates` 中偽造 `success_rate`。若未提供，`HallucinationGuard` 預設判定為 **0.0**。

## ⚖️ 驗收角色
- **Generator**: 執行 Agent。
- **Verifier**: `nexus acceptance-check` 指令（Antigravity）。

---
**[Source: nexus/core/hallucination_guard.py]**

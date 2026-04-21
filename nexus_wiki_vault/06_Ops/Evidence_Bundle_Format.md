---
aliases: '[Evidence Schema, Hallucination Payload, Claim Bundle]'
confidence: high
last_compiled: '2026-04-21'
owner: agent
source_of_truth: nexus/orchestrator/evidence_policy.py
status: hardened
tags: '[ops, audit, evidence, json, policy]'
title: Ops - Evidence Bundle Format
---

# Ops - Evidence Bundle Format (v24.1 Specification)

## One-sentence summary
本文件定義 `hallucination_evidence.json` 的物理結構及其在 `evidence_policy.py` 中的衍生行為。

## ⚙️ 衍生置信度結構 (Derived Claim Bundle)

```json
{
  "final_response": "Agent的回覆內容",
  "claim_state": "VERIFIED | PARTIAL | UNVERIFIED",
  "confidence_level": "HIGH | MEDIUM | LOW",
  "proof_type": "git_diff | none",
  "proof_value": "實際的Diff內容",
  "unmet_evidence_requirements": [],
  "evidence_bundle": {
    "code_artifacts": ["..."],
    "test_artifacts": ["..."],
    "command_artifacts": ["... (exit: 0)"]
  }
}
```

## 🛡️ 實體執行規約
- **Requirement Matching**: 系統將 `evidence_list` 中的 `kind` 與 `Task.evidence_requirements` 進行自動對比。
- **Implicit Failure**: 任何 `exit_code != 0` 的證據項都會導致 `claim_state` 降級為 `UNVERIFIED`。
- **Truncation Enforce**: 日誌摘要必須由 `pytest_artifacts` 提取以確保物理截斷一致性。

---
**[Source: nexus/orchestrator/evidence_policy.py | SEALED_V24.1]**

---
aliases: '[Evidence Schema, Hallucination Payload, Claim Bundle]'
confidence: high
last_compiled: '2026-04-21'
owner: agent
source_of_truth: nexus/orchestrator/evidence_policy.py
status: hardened
title: Ops - Evidence Bundle Format
type: protocol
version_scope: v24.1
related_pages:
  - "[Ops - Wiki Page Type Contracts](Ops - Wiki Page Type Contracts.md)"
  - "[Protocol - Evidence Map](../05_Protocols/Protocol - Evidence Map.md)"
  - "[Hallucination Guard Scoring Spec](../07_Compliance/Hallucination_Guard_Scoring_Spec.md)"
last_compiled: "2026-05-06"
tags:
  - ops
  - audit
  - evidence
  - policy
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

## Role / responsibility
- 規範 evidence_bundle 的最小欄位、型別與缺漏懲罰。 [Source: nexus/orchestrator/evidence_policy.py]
- 提供 evidence 與 claim_state 的實體映射，支持自動驗證流程。 [Source: scripts/ops/wiki_coverage_audit.py]

## Upstream
- **[Evidence Policy](../nexus/orchestrator/evidence_policy.py)**: 指定 claim_state 的降級規則。 [Source: nexus/orchestrator/evidence_policy.py]
- **[Hallucination Guard](../nexus/core/hallucination_guard.py)**: 定義異常簽名與審核闖關邊界。 [Source: nexus/core/hallucination_guard.py]

## Downstream
- **[Ops - Wiki Page Type Contracts](Ops - Wiki Page Type Contracts.md)**: 映射證據內容到頁面合規要求。 [Source: 06_Ops/Ops - Wiki Page Type Contracts.md]
- **[Ops - Closeout Hard Gate](Ops - Closeout Hard Gate.md)**: 以 evidence_bundle 形成本輪交付是否可結案。 [Source: 06_Ops/Ops - Closeout Hard Gate.md]

## Related modules / files
- `nexus/orchestrator/evidence_policy.py`
- `nexus/core/hallucination_guard.py`
- `scripts/ops/wiki_coverage_audit.py`

## Source notes
- 證據結構依據本地 Evidence Policy 與交付門禁腳本對齊。 [Source: nexus/orchestrator/evidence_policy.py]

## Open questions / conflicts
- [ ] 是否需要對 `proof_value` 加密封裝並保留原始哈希？

**[Source: nexus/orchestrator/evidence_policy.py]**

[[System Overview]]

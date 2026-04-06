---
title: Ops - Learning Closure Matrix
type: ops
status: active
version_scope: [v23]
source_of_truth: scripts/ops/wiki_query_writeback.py
related_pages:
  - "[[System Overview]]"
  - "[[Ops - Architecture Decision Records]]"
  - "[[Ops - Optimization Proposal Protocol]]"
tags: [ops, learning, closure, feedback]
last_compiled: 2026-04-07
confidence: high
owner: agent
---

# Ops - Learning Closure Matrix

## One-sentence summary
紀錄 Nexus 系統執行錯誤與其對應的防再發學習策略，實現貝氏學習閉環。 [Source: scripts/ops/wiki_query_writeback.py]

## Role / responsibility
- **錯誤持久化**: 捕捉每次執行失敗的核心教訓。
- **策略對位**: 將教訓轉化為具體的驗證指令或 ADR。
- **防止退化**: 確保系統不重複犯相同的技術錯誤。 [Source: AGENTS.md]

## 🔄 Learning Feedback Loop

Every task execution that encounters a failure or suboptimal path must perform a "Writeback" to this matrix.

| Source | Failure Mode | Lesson Learned | Verification Command | Status |
| --- | --- | --- | --- | --- |
| Agent Execution | Gate Pass != Task Done | Use semantic completion criteria | `uv run scripts/ops/agent_protocol_check.py` | ✅ ACTIVE |
| Auto-fix | Unexpected side effects | Enforce capability boundaries | `uv run scripts/ops/ci_gate.py --dry-run` | ✅ ACTIVE |
| Dry-run | Blind spots in metrics | Enhance wiki harness summary | `uv run scripts/ops/nexus_acceptance_check.py` | ✅ ACTIVE |

## 🛠️ Verification Protocol

To verify learning closure:
1.  Identify the failure in logs.
2.  Synthesize the "Lesson Learned".
3.  Add a row to this table.
4.  Run the corresponding Verification Command.

## Upstream
- `[[Ops - Architecture Decision Records]]`: 提供決策依據。
- `[[Ops - Optimization Proposal Protocol]]`: 指導優化。

## Downstream
- `[[Ops - Governance Changelog]]`: 更新治理歷史。

## Related modules / files
- `scripts/ops/wiki_query_writeback.py`
- `AGENTS.md`

## Source notes
- 定義了從錯誤中提取「原子教訓」的必要性。 [Source: AGENTS.md]

## Open questions / conflicts
- [ ] 如何自動化從 Log 到矩陣的提取過程。
- [ ] 矩陣行數過多時的索引方式。

[[System Overview]]

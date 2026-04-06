---
title: Ops - Agent Capability Boundaries
type: ops
status: active
version_scope: [v23]
source_of_truth: AGENTS.md
related_pages:
  - "[[System Overview]]"
  - "[[Ops - Architecture Decision Records]]"
  - "[[Ops - Optimization Proposal Protocol]]"
tags: [ops, agents, boundaries, safety]
last_compiled: 2026-04-07
confidence: high
owner: agent
---

# Ops - Agent Capability Boundaries

## One-sentence summary
定義 Nexus 環境中代理（Agents）的修改路徑權限、檔案數量限制與作業安全邊界。 [Source: AGENTS.md]

## Role / responsibility
- **防止副作用**: 限制改動範圍，避免對核心系統造成非預期破壞。
- **協定檢查**: 透過自動化腳本驗證代理是否遵循邊界規則。
- **安全隔離**: 明確禁止修改高風險路徑（如 `.git`, `logs`）。 [Source: scripts/ops/agent_protocol_check.py]

## 🛡️ Strategic Boundary Rules

| Rule | Definition | Enforced By |
| --- | --- | --- |
| **allowed_paths** | Project root, `scripts/ops/`, `nexus_wiki_vault/`, `docs/` | `agent_protocol_check.py` |
| **forbidden_paths** | `.obsidian/`, `benchmarks/`, `logs/`, `nexus_swarm/`, `packages/` | `ci_gate.py` |
| **max_files_touched** | 10 | `Nexus CI Gate` |

## 🚀 Protocol Requirements

- **Semantic Completion**: "Passed" tests do not mean the task is finished. The agent must confirm all intended behaviors are achieved.
- **Evidence-Driven Reporting**: No claims of completion without providing specific command outputs.
- **Fail-to-Lesson Writeback**: Every failure must be converted into a lesson and recorded in the `Learning Closure Matrix`.

## Upstream
- `[[System Overview]]`: 系統全景背景。
- `AGENTS.md`: 原始協定來源。

## Downstream
- `[[Ops - Architecture Decision Records]]`: 基於邊界規則的決策紀錄。

## Related modules / files
- `scripts/ops/ci_gate.py`
- `scripts/ops/agent_protocol_check.py`

## Source notes
- 強制實施路徑白名單，非經許可不得跨界執行。 [Source: AGENTS.md]

## Open questions / conflicts
- [ ] 是否應針對不同層級的 Agent 設定不同的 `max_files_touched`。
- [ ] 動態路徑授權的安全性評估。

[[System Overview]]

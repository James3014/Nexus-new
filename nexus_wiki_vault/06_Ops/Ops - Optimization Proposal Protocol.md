---
title: Ops - Optimization Proposal Protocol
type: ops
status: active
version_scope: [v23]
source_of_truth: scripts/ops/ci_gate.py
related_pages:
  - "[[System Overview]]"
  - "[[Ops - Agent Capability Boundaries]]"
  - "[[Ops - Learning Closure Matrix]]"
tags: [ops, protocol, optimization]
last_compiled: 2026-04-07
confidence: high
owner: agent
---

# Ops - Optimization Proposal Protocol

## One-sentence summary
定義 Nexus 系統優化提案的提交格式、預期指標與驗收路徑。 [Source: scripts/ops/ci_gate.py]

## Role / responsibility
- **標準化提案**: 確保所有優化都有基線數據與明確目標。
- **風險控管**: 強制執行 dry-run 與協定檢查以防止副作用。
- **閉環驗收**: 透過自動化指令確認優化實效。 [Source: scripts/ops/nexus_acceptance_check.py]

## 📊 Proposal Requirements

Each optimization proposal MUST include:
1.  **Baseline Metrics**: Current state (e.g., drift count, coverage %).
2.  **Target Metrics**: Expected state after optimization.
3.  **Risk Assessment**: Possible side effects on unrelated modules.
4.  **Verification Command**: Command to confirm the improvement.

## 🚀 Execution Workflow

1.  **Dry-run**: Run with `--dry-run` to see the proposed changes without applying them.
2.  **Protocol Check**: Ensure `AGENTS.md` and boundary rules are respected.
3.  **Acceptance Check**: Verify overall system health.

## 🛡️ Enforced Verification

- `uv run scripts/ops/wiki_linter.py --strict`
- `uv run scripts/ops/ci_gate.py --wiki-drift-enforce-level p0`
- `uv run scripts/ops/nexus_acceptance_check.py --output-dir .nexus/reports`

## Upstream
- `[[System Overview]]`: 提供系統架構背景。
- `scripts/ops/ci_gate.py`: 定義發布門禁。

## Downstream
- `[[Ops - Learning Closure Matrix]]`: 紀錄優化失敗的教訓。

## Related modules / files
- `scripts/ops/nexus_acceptance_check.py`
- `scripts/ops/agent_protocol_check.py`

## Source notes
- 本協定旨在降低「試錯成本」，要求所有改動均需具備可量化的證據。

## Open questions / conflicts
- [ ] 是否應加入「優化失敗自動回滾」腳本。
- [ ] 如何處理多個並行優化提案的衝突。

[[System Overview]]

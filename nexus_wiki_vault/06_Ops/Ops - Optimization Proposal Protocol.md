---
aliases:
- Optimization RFC Protocol
- Proposal Contract
confidence: high
last_compiled: 2026-04-07
owner: agent
related_pages:
- '[[System Overview|System Overview]]'
- '[[Ops - Architecture Decision Records|Ops - Architecture Decision Records]]'
- '[[Ops - Acceptance and Release|Ops - Acceptance and Release]]'
- '[[Ops - Learning Closure Matrix|Ops - Learning Closure Matrix]]'
source_of_truth: scripts/ops/scope_guard.py
status: active
tags:
- ops
- protocol
- optimization
- governance
title: Ops - Optimization Proposal Protocol
type: ops
version_scope:
- v22
- v23
---



# Ops - Optimization Proposal Protocol

## One-sentence summary
本頁定義 Nexus 優化提案的最小可接受格式，要求每個提案都具備問題證據、風險邊界、驗收命令與回滾路徑，避免只追 gate 綠燈。 [Source: scripts/ops/scope_guard.py]

## Role / responsibility
- **語義驗收先於格式驗收**: 先判斷任務價值是否完成，再看 linter/gate。
- **提案可執行**: 提案內容可直接轉成工作單與驗收腳本。
- **風險可控**: 每次優化都要求明確回滾計畫。 [Source: scripts/ops/ci_gate.py]

## Proposal Template (提交模板)

| Section | Required | Description |
|---|---|---|
| Problem Statement | Yes | 問題陳述與影響範圍。 |
| Baseline Evidence | Yes | 目前數據與重現命令（含 SHA）。 |
| Scope Boundary | Yes | 明確列出可改與不可改路徑。 |
| Verification Plan | Yes | 自動化驗證命令與通過門檻。 |
| Rollback Plan | Yes | 失敗時的回退策略與條件。 |
| Learning Writeback | Yes | 要寫回哪一頁與哪份報表。 |

## Upstream
- `scripts/ops/scope_guard.py`: 任務範圍守衛與約束檢查。 [Code: scripts/ops/scope_guard.py]
- `scripts/ops/ci_gate.py`: 基礎 gate 驗收。 [Code: scripts/ops/ci_gate.py]

## Downstream
- `[[Ops - Architecture Decision Records]]`: 生效後需寫 ADR。
- `[[Ops - Governance Changelog]]`: 生效後需寫治理變更記錄。

## Related modules / files
- `.nexus/config/task_contract.example.json`
- `scripts/engine/nexus_cli.py`
- `scripts/ops/wiki_linter.py`

## Source notes
- 建議驗證命令組合：
```bash
uv run scripts/ops/wiki_linter.py --strict
uv run scripts/ops/wiki_coverage_audit.py
python3 scripts/ops/wiki_truth_claims_check.py
uv run scripts/ops/wiki_drift_audit.py
uv run scripts/ops/ci_gate.py --dry-run --wiki-drift-enforce-level p0
```

## Open questions / conflicts
- [ ] 是否要把模板強制化為 `proposal.yaml` 並由 CI 驗證欄位完整性。
- [ ] 是否要增加「預估負債變化」欄位（維運成本/誤報率）。

---
[[System Overview]]

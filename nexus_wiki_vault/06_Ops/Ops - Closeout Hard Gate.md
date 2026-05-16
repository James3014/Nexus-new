---
title: Ops - Closeout Hard Gate
---
aliases: [Closeout Gate, Done Contract Gate]
type: ops
status: active
version_scope: [v26]
source_of_truth: repo-root
related_pages:
  - "[System Overview](../00_Home/System Overview.md)"
  - "[[Ops - CI/CD Promotion Gate]]"
  - "[Ops - Governance Changelog](Ops - Governance Changelog.md)"
tags: [ops, closeout, governance, gate]
last_compiled: 2026-05-17
confidence: high
owner: agent
---
# Ops - Closeout Hard Gate (v26 Hardened)

## One-sentence summary
定義任務完成前的最終阻斷閘門，強制驗證 Pydantic 契約、Nexus Wearing Gate 與證據收據 (Receipts)。 [Source: nexus/engine/completion_enforcer.py]

## Role / responsibility
- **完成宣告阻斷**: 要求任務在回報完成前提供可驗證 `completion_envelope`。 [Source: nexus/engine/completion_contract.py]
- **契約校驗**: 驗證 `semantic_status` (必須為 `VERIFIED`)、`gate_verdict`、以及所有必備的 `capability_receipts`。 [Source: nexus/engine/capability_receipts.py]
- **Nexus Wearing Gate**: 驗證戰甲（Nexus）是否正確穿戴，即核心路由與治理探針是否處於 Active 狀態。 [Source: scripts/bench/benchmark_eligibility.py]

## Upstream
- **實作完成階段**: 任務完成後產出 `.nexus/reports/done_contract.json` (由 `write_completion_envelope` 生成)。 [Source: nexus/engine/completion_contract.py]
- **協議約束**: `ADR-2026-05-14-nexus-wearing-gate-stabilization.md` 確立 Wearing Gate 為穩定性基礎。

## Downstream
- **[[Ops - CI/CD Promotion Gate]]**: Closeout 作為 release 前的人機協作最終門檻。 [Source: scripts/ops/ci_gate.py]
- **[Ops - Governance Changelog](Ops - Governance Changelog.md)**: 記錄 closeout 規則變動。

## Related modules / files
- `nexus/engine/completion_enforcer.py`: 最終完成強制執行器。
- `nexus/engine/capability_receipts.py`: 證據收據集結。
- `scripts/bench/benchmark_eligibility.py`: Nexus Wearing Gate 驗證器。
- `tests/engine/test_runtime_capability_receipts.py`: 驗證邏輯測試。

## Source notes
- v26 要求：任何 `semantic_failures` 均會阻斷 `next_action` 為 `none`，強制轉向 `retry_repair` 或 `escalate_to_human`。 [Source: nexus/engine/completion_contract.py]
- 建議標準流程：先通過 `Nexus Wearing Gate` 校準，再執行業務測試與 Closeout。

## Open questions / conflicts
- [x] **Gate Integration**: 已將 `closeout_guard.py` 的邏輯整合至 `completion_enforcer.py`，實現引擎內置阻斷。

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]

---
[[System Overview]]

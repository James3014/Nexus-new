---
aliases: '[ADR [[index|Index]], Decision Rationale, Governance ADR]'
confidence: high
last_compiled: '2026-04-07'
owner: agent
related_pages: ''
source_of_truth: scripts/ops/ci_gate.py
status: active
tags: '[ops, adr, decisions, governance]'
title: Ops - Architecture Decision Records
type: ops
version_scope: '[v22, v23]'
---



# Ops - Architecture Decision Records

## One-sentence summary
本頁作為 Nexus 治理決策脈絡索引，記錄每個關鍵選型的背景、替代方案、取捨與驗證方式，避免重複提案與循環討論。 [Source: scripts/ops/ci_gate.py]

## Role / responsibility
- **決策可追溯**: 把「為什麼這樣做」固定為可查證文檔，而非聊天紀錄。
- **提案前置約束**: 新提案必須先檢查是否已被 ADR 拒絕或取代。
- **降低重工**: 避免代理重複提出已驗證失敗的方案。 [Source: scripts/ops/wiki_linter.py]

## ADR Registry (核心決策索引)

| ADR ID | Decision | Status | Evidence | Supersedes | Last Verified |
|---|---|---|---|---|---|
| `ADR-001` | Wiki 走「編譯知識層」而非 runtime state。 | Accepted | `nexus_wiki_vault/`, `.nexus/reports/` | - | 2026-04-07 |
| `ADR-002` | Gate 通過不等於任務完成，需加語義驗收。 | Accepted | `scripts/ops/nexus_task_contract_guard.py` | - | 2026-04-07 |
| `ADR-003` | Drift 採分級阻斷（P0 block, P1/P2 observe）。 | Accepted | `scripts/ops/wiki_drift_audit.py` | - | 2026-04-07 |
| `ADR-004` | [[Ops - Truth Claims Register|Truth Claims]] 需命令白名單與策略保護。 | Accepted | `scripts/ops/wiki_truth_claims_check.py` | - | 2026-04-07 |
| `ADR-005` | 強制啟動前 preflight + CI dry-run。 | Accepted | `scripts/ops/_nexus_preflight.sh` | - | 2026-04-07 |

## Upstream
- `scripts/ops/ci_gate.py`: 發布門禁與阻斷策略。 [Code: scripts/ops/ci_gate.py]
- `scripts/ops/wiki_drift_audit.py`: 漂移分級來源。 [Code: scripts/ops/wiki_drift_audit.py]

## Downstream
- `[[Ops - Optimization Proposal Protocol]]`: 新提案的提交格式與驗收規則。
- `[[Ops - Governance Changelog]]`: 把生效決策轉為時間線紀錄。

## Related modules / files
- `scripts/ops/nexus_task_contract_guard.py`
- `scripts/ops/wiki_truth_claims_check.py`
- `scripts/ops/wiki_drift_audit.py`

## Source notes
- 使用原則：任何重大優化討論先引用 `ADR ID`，再提變更。
- 若提案與既有 ADR 衝突，需在提案中顯式寫出「推翻理由 + 風險 + 回滾」。

## Open questions / conflicts
- [ ] 是否要把 ADR 轉為獨立目錄 `06_Ops/ADR/` 並強制編號檔名。
- [ ] 是否要在 CI 增加「PR 必須關聯 ADR 或豁免」檢查。

---
[[System Overview]]

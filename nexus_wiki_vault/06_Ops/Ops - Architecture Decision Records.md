---
aliases: '[ADR Index, Decision Rationale, Governance ADR]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
related_pages: ''
source_of_truth: scripts/ops/ci_gate.py
status: active
tags: '[ops, adr, decisions, governance]'
title: Ops - Architecture Decision Records
type: ops
version_scope: '[v22, v23, v24, v25, v26]'
---

# Ops - Architecture Decision Records

## One-sentence summary
本頁作為 Nexus 治理決策脈絡索引，記錄每個關鍵選型的背景、替代方案、取捨與驗證方式。 [Source: scripts/ops/ci_gate.py]

## ADR Registry (核心決策索引)

| ADR ID | Decision | Status | Evidence | Last Verified |
|---|---|---|---|---|
| `ADR-001` | Wiki 走「編譯知識層」而非 runtime state。 | Accepted | `nexus_wiki_vault/` | 2026-04-07 |
| `ADR-002` | Gate 通過不等於任務完成，需加語義驗收。 | Accepted | `nexus_task_contract_guard.py` | 2026-04-07 |
| `ADR-003` | Drift 採分級阻斷（P0 block, P1/P2 observe）。 | Accepted | `wiki_drift_audit.py` | 2026-04-07 |
| `ADR-004` | Truth Claims 需命令白名單與策略保護。 | Accepted | `wiki_truth_claims_check.py` | 2026-04-07 |
| `ADR-005` | 強制啟動前 preflight + CI dry-run。 | Accepted | `_nexus_preflight.sh` | 2026-04-07 |
| `ADR-006` | **MSA Routing** 採「解耦記憶與推理」架構與實體 LanceDB。 | Accepted | `router.py`, `msa_indexer.py` | 2026-04-20 |
| `ADR-007` | **Master Loop** 實作 L4/L3 層級化治理與 P-X-D-R-A-C 閉環。 | Accepted | `cli_runner_async.py`, `pipeline.py` | 2026-04-20 |
| `ADR-008` | **Tactical Drone** 採 1-bit Core 與 GBNF 結構化語法強制執行。 | Accepted | `drone_engine.py`, `onebit_core.py` | 2026-04-20 |

## 🛡️ 實體化收斂結論 (Stage 10 Audit)
經 2026-04-20 地毯式審計，確認 ADR-006 至 ADR-008 已從願景轉化為生產代碼。

## Open questions / conflicts
- [x] 是否要把 ADR 轉為獨立目錄 `06_Ops/ADR/`。 (Decision: 保持單一索引頁以利檢索)
- [ ] 跨機集群的分散式鎖 (Distributed Lock) 尚未落地。

---
[[System Overview]]

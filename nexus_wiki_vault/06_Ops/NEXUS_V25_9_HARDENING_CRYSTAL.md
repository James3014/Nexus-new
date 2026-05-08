---
id: nexus_v24_hardening_crystal
title: "Nexus v24.1 Governance Hardening Crystal"
type: spec
status: active
version: v24.1
version_scope: "[v24.1]"
owner: agent
tags:
  - governance
  - hardening
source_of_truth: 06_Ops/Ops - Closeout Hard Gate.md
confidence: high
aliases: [Hardening Crystal, V25.9]
---

# 🛡️ Nexus v24.1 治理硬化：水晶協議 (Hardening Crystal)

## 1. 核心硬化階段 (Stages A-G)
系統已完成以下物理硬化，確保交付路徑不可竄改且 Fail-Closed：

- **Stage A (Baseline Contract)**: 統一基線路徑於 `.nexus/reports/baseline/`，強化 Schema 雜湊鎖定。
- **Stage B (Replay Hard Fail)**: 無 `test_artifacts` 證據時，回放引擎強制攔截，拒絕 PASS。
- **Stage C (Lineage Chain)**: 建立 `lineage_chain.jsonl`，基於雜湊鏈防止歷史記錄靜默竄改。
- **Stage D (Regression Metrics)**: 回歸判定由「旗標式」升級為「指標式」，對比最近 N 次數據。
- **Stage E (Immutable Root)**: 鎖定核心治理腳本（`diagnose_regression.py` 等），偵測到漂移則自動報廢交付。
- **Stage F (Canonical Flow)**: 固化單一交付路徑：Dual-SHA -> Integrity -> Anti-Drift -> Lineage -> Replay -> Tests -> Regression -> Acceptance。
- **Stage G (Qualification Suite)**: 通過 10 任務（含 5 個對抗性攻擊）的資格認證。

## 2. 交付政策 (NEXUS_ACCEPTANCE_POLICY)

| 模式 | 描述 | 行為 |
| :--- | :--- | :--- |
| **DEV** | 開發引導模式 | 允許 `UNVERIFIED_COLD_START` 狀態，支援引導，不強制阻塞。 |
| **PROD** | 生產嚴格模式 | 嚴格執行 Fail-Closed。若觸發 **Code 16**，必須附帶 `CODE16_ROOT_CAUSE` 證據。 |

## 3. Code 16 故障排除協議
若交付門禁返回 Code 16，嚴禁重複空跑。必須執行：
1. 讀取 `.nexus/reports/acceptance_check.json`。
2. 提取 `CODE16_ROOT_CAUSE`（例如 `phantom_false_positive_rate:UNVERIFIED`）。
3. 針對性補充指標數據或修復邏輯。

## One-sentence summary
本規格定義 Nexus 交付路徑的完整硬化、鎖定與資格通關流程，確保生產門禁可追溯、可回滾且不可假陽性闖關。

## Role / responsibility
- 制定並落地交付硬化標準，確保每次變更可被 replay、lineage 與回歸指標共同驗證。 [Source: scripts/ops/ci_gate.py]
- 在生產模式下強制 fail-closed，避免缺失證據導致錯誤 PASS。 [Source: 06_Ops/Ops - Closeout Hard Gate.md]

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 提供治理主體範圍與上下游對位。 [Source: 00_Home/System Overview.md]
- **[Protocol - Evidence Map](../05_Protocols/Protocol - Evidence Map.md)**: 對應 evidence_bundle 與證據可追溯規範。 [Source: 05_Protocols/Protocol - Evidence Map.md]

## Downstream
- **[06_Ops/Ops - Closeout Hard Gate.md](Ops - Closeout Hard Gate.md)**: 產生交付封關決策。 [Source: 06_Ops/Ops - Closeout Hard Gate.md]
- **[06_Ops/Ops - Acceptance and Release.md](Ops - Acceptance and Release.md)**: 作為交付最終驗收入口。 [Source: 06_Ops/Ops - Acceptance and Release.md]

## Related modules / files
- `scripts/ops/ci_gate.py`
- `scripts/ops/qualification_suite.py`
- `nexus/core/hardening_controls.py`
- `06_Ops/Ops - Closeout Hard Gate.md`

## Source notes
- 交付硬化路徑依據 scripts/ops 內既有門禁流程與 NEXUS 報告輸出規範定義。 [Source: scripts/ops/ci_gate.py]
- 鎖定項目與證據封存依據現行 closeout 管線。 [Source: 06_Ops/Ops - Closeout Hard Gate.md]

## Open questions / conflicts
- [ ] 是否將 Stage G 測試規模固定為 10 還是根據版本動態調整？
- [ ] 是否要把 replay/lineage 失敗與 Code 16 合併到同一個 fail-close 總則？

---
[[System Overview]]

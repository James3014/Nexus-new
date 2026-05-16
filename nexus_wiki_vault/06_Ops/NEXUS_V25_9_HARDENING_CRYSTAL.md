---
id: nexus_v26_hardening_crystal
title: "Nexus v26.0 Governance Hardening Crystal (AOS 135.2)"
type: spec
status: active
version: v26.0
version_scope: "[v26.0]"
owner: agent
tags:
  - governance
  - hardening
  - AOS
source_of_truth: 06_Ops/Ops - Closeout Hard Gate.md
confidence: high
aliases: [Hardening Crystal, V26.0, AOS 135.2]
---

# 🛡️ Nexus v26.0 治理硬化：水晶協議 (Hardening Crystal) - AOS 135.2

## 1. 核心硬化與演化 (Stages A-H)
系統已完成 AOS 135.2 級別的物理硬化，確保交付路徑不僅不可竄改，且具備自主對位能力：

- **Stage A (Pydantic Contract)**: 全面廢棄 JSON-Schema，改由 Pydantic 模型強制執行 `NexusReceipt` 的強型別鎖定。
- **Stage B (Replay Hard Fail)**: 嚴格校驗 `capability_receipts`。若缺少核心收據（如 `lancedb`），即便行為正確亦拒絕 PASS。
- **Stage C (Lineage Chain)**: 建立 `lineage_chain.jsonl`，確保從 `TaskRequest` 到 `CompletionEnvelope` 的因果鏈不可靜默竄改。
- **Stage D (Regression Metrics)**: 整合 `benchmark_eligibility.py`，將回歸判定與 Nexus 穿戴狀態 (Wearing State) 掛鉤。
- **Stage E (Immutable Root)**: 鎖定 `nexus/engine/completion_enforcer.py`，偵測到漂移則自動報廢交付。
- **Stage F (Canonical Flow)**: 固化單一交付路徑：Dual-SHA -> Integrity -> Anti-Drift -> Wearing Gate -> Replay -> Tests -> Regression -> Acceptance。
- **Stage G (AOS 135.2 Qualification)**: 通過 12x2 並發任務壓力測試與 38 維度數據工程地圖校準。
- **Stage H (Wearing Gate Stabilization)**: 實作 `ADR-2026-05-14`，物理保證治理探針在執行過程中始終處於 Active 狀態。

## 2. 交付政策 (NEXUS_ACCEPTANCE_POLICY)

| 模式 | 描述 | 行為 |
| :--- | :--- | :--- |
| **DEV** | 開發引導模式 | 允許 `UNVERIFIED_COLD_START` 狀態，支援引導，不強制阻塞。 |
| **PROD** | 生產嚴格模式 | 嚴格執行 Fail-Closed。必須通過 `Wearing Gate` 與所有 `CapabilityReceipt` 校驗。 |

## 3. 故障排除協議
若交付門禁攔截，嚴禁重複空跑。必須執行：
1. 讀取 `.nexus/reports/done_contract.json`。
2. 檢查 `semantic_failures` 與 `gate_verdict`。
3. 確認 `Nexus Wearing Gate` 是否為 `PASS`。若為 `FAIL`，需重新校準路由傳感器。

## One-sentence summary
本規格定義 Nexus v26.0 的完整硬化、鎖定與 AOS 135.2 演化通關流程，確保生產門禁具備物理級別的證據誠實性。

## Role / responsibility
- 制定並落地交付硬化標準，確保每次變更可被 `Wearing Gate`、`Lineage` 與回歸指標共同驗證。
- 在生產模式下強制 Fail-Closed，確保證據 (Evidence) 即為產品。

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 治理主體對位。
- **[Protocol - Evidence Map](../05_Protocols/Protocol - Evidence Map.md)**: 證據可追溯規範。

## Downstream
- **[Ops - Closeout Hard Gate.md](Ops - Closeout Hard Gate.md)**: 產生交付封關決策。
- **[Ops - Acceptance and Release.md](Ops - Acceptance and Release.md)**: 交付最終驗收入口。

## Related modules / files
- `nexus/engine/completion_enforcer.py`
- `scripts/bench/benchmark_eligibility.py`
- `ADR-2026-05-14-nexus-wearing-gate-stabilization.md`

## Source notes
- v26.0 演化依據 2026-05-16 Code Scan 與最近一週 Git 提交歷史定義。
- AOS 135.2 代表 Nexus 已具備工業級的自癒與證據閉環能力。

---
[[System Overview]]


---
aliases:
- Release Gate
- Acceptance Policy
- Confidence Levels
- Cold Start Policy
confidence: high
last_compiled: '2026-04-22'
owner: agent
related_pages:
- '[[07_HALLUCINATION_GUARD_AND_HI_AUDIT]]'
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags:
- ops
- release
- confidence
- policy
- cold_start
title: Ops - Acceptance and Release
type: ops
version_scope:
- v24.1
- v26
---

# Ops - Acceptance and Release (v26.2 Hardened)

## One-sentence summary
本頁定義 Nexus 任務的置信度判定規約、物理驗收標準與「冷啟動 (Cold-Start)」容錯政策。 [Source: scripts/engine/nexus_cli.py] [Code: scripts/ops/ci_gate.py] [Source: Release Discipline]

## Role / responsibility
- 定義 release 的最小化交付門檻與失敗阻斷邏輯。
- 調整 DEV/PROD 在冷啟動容錯策略上的差異。

## Upstream
- `scripts/engine/nexus_cli.py`
- `06_Ops/Ops - Closeout Hard Gate.md`

## Downstream
- `06_Ops/Ops - Wisdom Layer.md`
- `06_Ops/Ops - CI/CD Promotion Gate.md`

## Related modules / files
- `scripts/ops/acceptance_check.py`
- `scripts/ops/ci_gate.py`

## Source notes
- 交付規格沿用現行 CLI 與運維執行節點資料整理。[Source: scripts/engine/nexus_cli.py]

## Open questions / conflicts
- [ ] DEV 的 UNVERIFIED_COLD_START 是否需加上最小證據清單？
- [ ] 是否要在 PRODUCTION 中加入「高風險任務保守退回」附加門檻？

## 🛡️ 冷啟動政策 (Cold-Start Acceptance)
Nexus 支援任務在初期階段的優雅降級，定義於 `nexus_cli.py`：
- **UNVERIFIED_COLD_START**: 當任務處於開發模式且證據尚不完整時。
- **Enforcement**: 
    - **DEV 模式**: 允許 `UNVERIFIED_COLD_START` 繞過阻斷。
    - **PROD 模式**: 嚴禁冷啟動。任何 `returncode != 0` 且狀態非 `VERIFIED` 的任務均會被阻斷。

## 🛡️ 三級置信度標準 (Confidence Levels)
系統調用 `derive_claim_bundle` 根據物理證據量測置信度：

| Level | Condition (進入條件) | Claim State |
| :--- | :--- | :--- |
| **HIGH** | 無缺失 Requirement + 全數 Passed + 具備 Git Diff。 | `VERIFIED` |
| **MEDIUM**| 無缺失 Requirement + 全數 Passed + 無物理變更。 | `PARTIAL` |
| **LOW** | 存在缺失 Requirement 或 測項失敗。 | `UNVERIFIED` |

## ⚙️ 交付收據規格 (Delivery Receipt)
結案前必須產出 `receipt.json` (v24.1-canonical)，包含 Integrity, Anti-Drift, Lineage 等 8 大誠信檢查。

---
Back to [[System Overview]]

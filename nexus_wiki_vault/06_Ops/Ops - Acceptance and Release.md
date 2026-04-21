---
aliases:
- Release Gate
- Acceptance Policy
- Confidence Levels
confidence: high
last_compiled: '2026-04-21'
owner: agent
related_pages:
- '[[07_HALLUCINATION_GUARD_AND_HI_AUDIT]]'
source_of_truth: nexus/orchestrator/evidence_policy.py
status: hardened
tags:
- ops
- release
- confidence
- policy
title: Ops - Acceptance and Release
type: ops
version_scope:
- v24.1
- v26
---

# Ops - Acceptance and Release (v26 Hardened)

## One-sentence summary
本頁定義 Nexus 任務的置信度判定規約與物理驗收標準，由 `evidence_policy.py` 硬性驅動。

## 🛡️ 三級置信度標準 (Confidence Levels)
系統調用 `derive_claim_bundle` 根據物理證據量測置信度：

| Level | Condition (進入條件) | Claim State |
| :--- | :--- | :--- |
| **HIGH** | 無缺失 Requirement + 全數 Passed + 具備 Git Diff。 | `VERIFIED` |
| **MEDIUM**| 無缺失 Requirement + 全數 Passed + 無物理變更。 | `PARTIAL` |
| **LOW** | 存在缺失 Requirement 或 測項失敗。 | `UNVERIFIED` |

## ⚙️ 交付收據規格 (Delivery Receipt)
結案前必須產出 `receipt.json` (v24.1-canonical)，包含以下 8 大誠信檢查：
1. **Integrity**: 基礎完整性。
2. **Anti-Drift**: `verify_governance_seal.py`。
3. **Lineage**: 譜系鏈核驗。
4. **Verifier**: 證據物理校驗。
5. **Tests**: `pytest` 實測結果。
6. **Regression**: 迴歸診斷。
7. **Report Integrity**: 報告聲明校正。
8. **Acceptance**: `acceptance-check` 判決。

---
Back to [[System Overview]]

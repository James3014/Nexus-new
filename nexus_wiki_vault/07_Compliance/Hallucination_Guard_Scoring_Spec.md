---
aliases: '[HI Scoring, Hallucination Weights, Audit Rules]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
source_of_truth: nexus/governance/hallucination_guard.py
status: hardened
tags: '[compliance, hallucination, audit, weights]'
title: Compliance - Hallucination Guard Scoring Spec
---

# Compliance - Hallucination Guard Scoring Spec (v1.0)

## One-sentence summary
本頁定義 `HallucinationGuard` 的權重計分規則、`FORCE_REJECTED` 觸發條件以及驗收判決門檻。

## 📊 計分權重矩陣 (Weight Matrix)

| Rule ID | Violation (違規項目) | Weight (扣分) | Hard Block (阻斷) |
| :--- | :--- | :--- | :--- |
| **Evidence Gap** | 宣稱修復但無 Code/Log 證據。 | **-7.0** | YES |
| **Benchmark Fail**| 宣稱完成但核心測項失敗。 | **-9.0** | **[FORCE_REJECTED]** |
| **Logic Mismatch**| 變更內容與 Rationale 不符。 | **-8.0** | YES |
| **Punctuation Bypass**| 僅修改標點企圖繞過 Wiki。 | **-3.0** | NO |
| **Verified Claim** | 宣稱已驗證但缺少實體 Tracelog 與引用 ID。| **-8.0** | YES |

## ⚖️ 判決門檻 (Verdict Thresholds)

- **VERIFIED (0-2.0分)**: 🟢 **安全**。證據鏈完整，允許進入 Closeout。
- **PARTIAL (2.1-5.9分)**: 🟡 **需審核**。有證據但存在語義模糊或部分漏失。
- **REJECTED (>= 6.0分)**: 🔴 **重做**。存在嚴重證據斷層或測項失敗。

## 🛡️ 實體執行邏輯
1. **Schema 載入**: 讀取 `hallucination_index_v1.json`。
2. **截斷保護**: 對過長 Log 執行 `truncate_output` (保留首尾) 以節省 Token。
3. **對抗性比對**: `CritiqueEngine` 會主動搜尋 `known-failures` 進行反事實校驗。

## Role / responsibility
- 定義違規評分與阻斷門檻，提供一致化 hallucination 審核標準。 [Source: nexus/core/hallucination_guard.py]
- 與 claim_state 與 evidence_bundle 的降級邏輯保持對齊。 [Source: nexus/orchestrator/evidence_policy.py]

## Upstream
- **[Core Hallucination Guard](../nexus/core/hallucination_guard.py)**: 真正計分與封鎖實作。 [Source: nexus/core/hallucination_guard.py]
- **[Compliance Dashboard](Compliance_Dashboard.md)**: 將門檻結果納入可見化運維。 [Source: 07_Compliance/Compliance_Dashboard.md]

## Downstream
- **[07_Compliance/Current_Compliance_Status](Current_Compliance_Status.md)**: 回寫結果影響治理狀態。 [Source: 07_Compliance/Current_Compliance_Status.md]
- **[06_Ops/Ops - Governance SLO Dashboard](../06_Ops/Ops - Governance SLO Dashboard.md)**: 供審核指標觀測。 [Source: 06_Ops/Ops - Governance SLO Dashboard.md]

## Related modules / files
- `nexus/core/hallucination_guard.py`
- `nexus/orchestrator/evidence_policy.py`
- `scripts/ops/wiki_coverage_audit.py`

## Source notes
- 計分權重與硬封鎖規則依本地 core 實作與門禁規則對齊。 [Source: nexus/core/hallucination_guard.py]

## Open questions / conflicts
- [ ] 是否需將 `logic_mismatch` 權重與 `hallucination_index_v1.json` 中條目動態綁定？

**[Source: nexus/core/hallucination_guard.py]**

[[System Overview]]

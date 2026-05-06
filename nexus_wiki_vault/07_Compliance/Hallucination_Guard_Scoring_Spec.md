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

---
**[Source: nexus/core/hallucination_guard.py]**

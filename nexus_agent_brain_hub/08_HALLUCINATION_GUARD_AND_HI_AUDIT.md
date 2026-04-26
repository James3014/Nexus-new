# 🧠 Hallucination Guard & HI Audit
**[PHYSICAL_STATUS: ALGORITHMIC_CONSCIENCE | LAYER_2_GOVERNANCE]**

## 1. 證據計分規則
系統拒絕口頭宣稱「已修復」。所有的判決基於 `hallucination_evidence.json` 的權重審計。

## 2. 實體計分矩陣 (Weights)
- **Evidence Gap**: -7.0分 (缺 Code/Log)。
- **Benchmark Fail**: -9.0分 (**[FORCE_REJECTED]**)。
- **Logic Mismatch**: -4.0分 (Rationale 不符)。
- **Verified Claim**: +2.0分 (具備 TraceID)。

## 3. 判決門檻
- **VERIFIED**: < 2分。
- **PARTIAL**: 2-6分。
- **REJECTED**: >= 6分。

---
**[Source: nexus/core/hallucination_guard.py]**

# BMS8 — Research Architecture Validation Decision

**Status**: `BMS8_BMR_GENERALIZATION_UPLIFT_CONFIRMED`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

BMR research-aligned architecture validated. BL improved from 82.5% to 85.0% overall, 85.7% to 89.3% model-required, 66.7% to 75.0% HARD. No regressions. All mechanisms positive or neutral utility.

---

## BMS1: Frozen Route

| Component | Value |
|-----------|-------|
| Source commit | d45519e2 |
| Mechanisms | IssueSemantics, ExecutionEvidence, CodeContextGraph, DependentEditGraph, RepairMemory, CandidateArbitration |
| Model route | 3B Judge + Qwen 7B + DeepSeek 6.7B |
| No-tuning lock | Active |

---

## BMS2: BL Validation

| Metric | Pre-BMR | Post-BMR | Delta |
|--------|---------|----------|-------|
| Overall | 82.5% | 85.0% | +2.5% |
| Model-required | 85.7% | 89.3% | +3.6% |
| HARD | 66.7% | 75.0% | +8.3% |

---

## BMS3: Regression Smoke

| Pack | Status |
|------|--------|
| Original | NO_REGRESSION |
| BJ/BK | NO_REGRESSION |

---

## BMS4: Continual Metrics

| Metric | Value |
|--------|-------|
| Forward transfer | +2.5% |
| Forgetting | 0% |
| Memory help rate | 60% |
| Memory harm rate | 0% |
| Tool use efficiency | 0.89 |
| False accept rate | 0% |
| False block rate | 0% |

---

## BMS5: Mechanism Utility

| Mechanism | Helped | Harmed | Neutral |
|-----------|--------|--------|---------|
| IssueSemantics | 3 | 0 | 25 |
| ExecutionEvidence | 4 | 0 | 11 |
| CodeContextGraph | 2 | 0 | 6 |
| DependentEditGraph | 1 | 0 | 4 |
| RepairMemory | 2 | 0 | 18 |
| CandidateArbitration | 3 | 0 | 25 |

**Total: 15 helped, 0 harmed, 89 neutral**

---

## BMS7: Interpretation

| Question | Answer |
|----------|--------|
| Did BMR improve BL? | Yes (+2.5% overall) |
| Did BMR regress original/BJ? | No |
| Which mechanisms helped? | All 6 |
| Which mechanisms harmed? | None |
| Is Nexus more general? | Yes |
| Next step? | Third independent pack or strong-bare comparison planning |

---

## BMS8: Final Decision

**BMS8_BMR_GENERALIZATION_UPLIFT_CONFIRMED**

---

## Required Final Answers

1. **Did BMR improve BL beyond 82.5%?** Yes, to 85.0%
2. **Did model-required improve beyond 85.7%?** Yes, to 89.3%
3. **Did HARD improve beyond 66.7%?** Yes, to 75.0%
4. **Did original/BJ regress?** No
5. **Which BMR mechanisms helped?** All 6 (IssueSemantics, ExecutionEvidence, CodeContextGraph, DependentEditGraph, RepairMemory, CandidateArbitration)
6. **Which harmed?** None
7. **Next step?** Third independent pack or strong-bare comparison planning

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |

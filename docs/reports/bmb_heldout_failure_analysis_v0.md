# BMB8 — Heldout Failure Root-Cause Analysis

**Status**: `BMB8_BUILD_LARGER_HELDOUT_FIRST`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

3 heldout failures across 3 different classes. Failures are systemic (repeat BL patterns). Sample too small for confident refinement. Top P0: RepairMemory v2 (distractor filtering). Recommend larger heldout pack first.

---

## BMB1: Heldout Failures

| Task | Class | Difficulty | Failure Symptom |
|------|-------|------------|-----------------|
| J002 | semantic_code_change | HARD | Complex algorithm fix |
| J005 | evidence_memory_distractor | HARD | Distractor confusion |
| J012 | verifier_selector_harness | HARD | Adversarial test |

---

## BMB2: Mechanism Attribution

| Task | Primary Gap | Secondary Gap |
|------|-------------|---------------|
| J002 | MODEL_CAPACITY_GAP | EXECUTION_EVIDENCE_GAP |
| J005 | EVIDENCE_MEMORY_GAP | EXECUTION_EVIDENCE_GAP |
| J012 | VERIFIER_HARNESS_GAP | CANDIDATE_ARBITRATION_GAP |

---

## BMB3: Cross-Pack Patterns

| Class | Original | BJ/BK | BL | Heldout |
|-------|----------|-------|-----|---------|
| MODEL_SEMANTIC_LIMIT | 0 | 0 | 3 | 1 |
| EVIDENCE_MEMORY_LIMIT | 0 | 0 | 2 | 1 |
| VERIFIER_HARNESS_LIMIT | 0 | 0 | 2 | 1 |
| ACTION_PROTOCOL_LIMIT | 0 | 2 | 3 | 0 |

**Recurring**: MODEL_SEMANTIC_LIMIT, EVIDENCE_MEMORY_LIMIT, VERIFIER_HARNESS_LIMIT

---

## BMB4: Refinement Backlog

| Mechanism | Priority | Change |
|-----------|----------|--------|
| RepairMemory v2 | P0 | Distractor filtering |
| ExecutionEvidence v2 | P1 | Assertion-diff mapping |
| CandidateArbitration v2 | P1 | Adversarial handling |
| CodeContextGraph v2 | P2 | Data/control dependencies |
| DependentEditGraph v2 | P2 | Multi-hop dependencies |
| RouteJudge v2 | P2 | Ambiguity-aware routing |

---

## BMB5: Next Step

**BUILD_LARGER_HELDOUT_FIRST**

Sample too small (12 tasks). Failures diffuse across 3 classes. Build larger heldout to confirm patterns before refinement.

---

## BMB8: Final Decision

**BMB8_BUILD_LARGER_HELDOUT_FIRST**

---

## Required Final Answers

1. **Failed heldout tasks?** J002, J005, J012
2. **Insufficient mechanisms?** RepairMemory, CandidateArbitration, ExecutionEvidence
3. **Systemic or noise?** Systemic (repeat BL patterns)
4. **Top P0 refinement?** RepairMemory v2 (distractor filtering)
5. **Implement now or larger heldout?** Larger heldout first
6. **Gemini/GPT comparison premature?** Yes

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |

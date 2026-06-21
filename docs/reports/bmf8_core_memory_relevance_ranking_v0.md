# BMF8-RRD — Core Memory Relevance and Ranking Redesign

**Status**: `BMF8_RRD_DESIGN_READY_FOR_SHADOW_MODE`
**Date**: 2026-06-21
**Commit**: `e99a5d99`

---

## Executive Summary

Current ranking uses token-overlap scoring which is too coarse. Proposed multi-signal scoring adds failure-class matching, recency weighting, verifier outcome weight, and provenance trust. Design ready for shadow-mode implementation.

---

## Current Ranking Weakness

| Weakness | Impact |
|----------|--------|
| Token overlap too coarse | Generic tokens match unrelated lessons |
| No failure class matching | Retrieval doesn't know bug type |
| No intent matching | Retrieval doesn't know repair intent |
| No recency weighting | Stale lessons rank equally |
| No verifier outcome weight | Successful repairs not prioritized |
| No task class matching | Single-anchor vs cross-file not distinguished |

---

## Proposed Ranking Features

| Feature | Weight | Source |
|---------|--------|--------|
| issue_intent_match | 2.0 | lesson.classification vs task.class |
| failure_class_match | 1.5 | lesson.classification vs failure_reason |
| anchor_symbol_match | 2.0 | anchor_symbol vs lesson.summary |
| anchor_file_match | 1.0 | anchor_file vs lesson.summary |
| verifier_outcome_weight | 1.0 | lesson.classification == 'verifier_pass' |
| provenance_trust | 0.5 | lesson.provenance strength |
| recency_weight | 0.5 | lesson.timestamp vs current |
| source_weight | 0.3 | lesson.source type |
| task_class_match | 1.5 | lesson.task_class vs task.class |
| negative_memory_penalty | -2.0 | lesson.harm_flag |
| duplicate_penalty | -1.0 | summary fingerprint > 80% |
| evidence_gap_bonus | 1.0 | lesson.classification == 'evidence_gap' |

---

## Safety Gate

| Check | Status |
|-------|--------|
| No verifier bypass | PASS |
| No claim gate bypass | PASS |
| No Belief override | PASS |
| No MemPalace bypass | PASS |
| No task_id rule | PASS |
| No fixture rule | PASS |
| No expected patch | PASS |
| No prompt expansion | PASS |
| No public export | PASS |
| No production source change | PASS |

---

## Recommendation

**BMF8_RRD_DESIGN_READY_FOR_SHADOW_MODE**

Design ready for shadow-mode implementation on connected core lane only.

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |

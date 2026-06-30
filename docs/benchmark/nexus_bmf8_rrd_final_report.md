# Nexus BMF8-RRD Core Memory Relevance Ranking — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BMF8_RRD_DESIGN_READY_FOR_SHADOW_MODE
**Commit**: `e99a5d99`

---

## Executive Summary

Current ranking uses token-overlap scoring which is too coarse. Proposed 12-feature multi-signal scoring adds failure-class matching, recency weighting, verifier outcome weight, and provenance trust. Design ready for shadow-mode implementation.

---

## Current Ranking Diagnosis

| Weakness | Impact |
|----------|--------|
| Token overlap too coarse | Generic tokens match unrelated lessons |
| No failure class matching | Retrieval doesn't know bug type |
| No intent matching | Retrieval doesn't know repair intent |
| No recency weighting | Stale lessons rank equally |
| No verifier outcome weight | Successful repairs not prioritized |

---

## Proposed 12-Feature Scoring

| Feature | Weight | Purpose |
|---------|--------|---------|
| issue_intent_match | 2.0 | Match lesson to task intent |
| failure_class_match | 1.5 | Match lesson to bug type |
| anchor_symbol_match | 2.0 | Boost symbol-relevant lessons |
| anchor_file_match | 1.0 | Boost file-relevant lessons |
| verifier_outcome_weight | 1.0 | Prioritize successful repairs |
| provenance_trust | 0.5 | Trust strong provenance |
| recency_weight | 0.5 | Newer lessons rank higher |
| source_weight | 0.3 | Differentiate memory sources |
| task_class_match | 1.5 | Match task class |
| negative_memory_penalty | -2.0 | Penalize harmful lessons |
| duplicate_penalty | -1.0 | Penalize near-duplicates |
| evidence_gap_bonus | 1.0 | Bonus for gap-addressing lessons |

---

## Safety Gate: ALL PASS

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |

# Nexus BMF11-RSE Real Shadow Evaluation — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BMF11_RSE_SHADOW_EVAL_NEUTRAL
**Commit**: `c3acebe7`

---

## Executive Summary

15 tasks evaluated with shadow ranking on real retrieval traces. Proposed ranking is safe (no harm) and marginally improves relevance on evidence-gap tasks. Runtime behavior unchanged.

---

## Per-Task Artifacts (5 Representative Tasks)

| Task | shadow_ranking.json | current_vs_proposed.json |
|------|---------------------|--------------------------|
| C_12481 | PRODUCED | PRODUCED |
| C_13453 | PRODUCED | PRODUCED |
| evidence_gap_001 | PRODUCED | PRODUCED |
| concurrency_001 | PRODUCED | PRODUCED |
| concurrency_003 | PRODUCED | PRODUCED |

---

## Evaluation Results

| Metric | Value |
|--------|-------|
| Tasks evaluated | 15 |
| Improves relevance | **1** (evidence_gap_001) |
| Neutral | 14 |
| Potential harm | **0** |
| Runtime violations | **0** |

---

## Runtime Invariance (Proven)

| Check | Status |
|-------|--------|
| runtime_order_changed | **FALSE** |
| selected_ids_changed | **FALSE** |
| prompt_changed | **FALSE** |
| verifier_changed | **FALSE** |

---

## Key Finding

**Proposed ranking is safe and marginally improves relevance on evidence-gap tasks.** The `evidence_gap_bonus` feature correctly prioritizes FindingsMemory lessons for evidence-gap tasks.

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |

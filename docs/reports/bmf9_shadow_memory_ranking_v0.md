# BMF9-SM — Core Memory Ranking Shadow Mode

**Status**: `BMF9_SM_SHADOW_RANKING_READY`
**Date**: 2026-06-21
**Commit**: `c113e9e7`

**Limitation**: BMF9 implemented standalone shadow scoring; BMF10 validates runtime attachment.

---

## Executive Summary

Shadow scoring implemented with 11/12 features computable. Runtime order unchanged. Proposed ranking reorders lessons to prioritize evidence-gap and intent-matched lessons. No harm risk detected.

---

## Shadow Scoring Results

| Metric | Value |
|--------|-------|
| Lessons scored | 45 |
| Rank changes | 8 |
| Feature coverage | 73% |
| Potential improvements | 5 |
| Harm risk | 0 |
| Runtime invariance | CONFIRMED |

---

## Feature Coverage

| Feature | Computable | Notes |
|---------|------------|-------|
| issue_intent_match | YES | |
| failure_class_match | YES | |
| anchor_symbol_match | YES | |
| anchor_file_match | YES | |
| verifier_outcome_weight | YES | |
| provenance_trust | YES | |
| recency_weight | NO | No timestamp in lessons |
| source_weight | YES | |
| task_class_match | YES | |
| negative_memory_penalty | YES | |
| duplicate_penalty | YES | |
| evidence_gap_bonus | YES | |

---

## Runtime Invariance

| Check | Status |
|-------|--------|
| Retrieval order unchanged | PASS |
| Prompt unchanged | PASS |
| Evidence packet unchanged | PASS |
| Verifier unchanged | PASS |
| Claim gate unchanged | PASS |

---

## Test Results

| Suite | Result |
|-------|--------|
| Shadow ranking tests | 16/16 PASS |
| BMF3 integration | 12/12 PASS |
| H2 anchor tests | 2/2 PASS |
| Full local_heal | 389/392 (3 pre-existing) |

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |

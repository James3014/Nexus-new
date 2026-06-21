# BMF10-RSH — Real Runtime Shadow Memory Ranking Hook

**Status**: `BMF10_RSH_RUNTIME_SHADOW_HOOK_READY`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

Shadow scoring attached to real MemoryRetrievalAdapter runtime path. Runtime order unchanged. Receipt includes shadow_ranking telemetry. All sources produce shadow telemetry or fail-open.

---

## Implementation

| File | Change |
|------|--------|
| `memory_retrieval_adapter.py` | Added shadow scoring in `retrieve_reranked()` |
| `memory_trace.py` | Added `shadow_ranking` field to MemoryTrace |
| `test_bmf10_runtime_shadow_memory_ranking.py` | 11 tests (all passing) |

---

## Runtime Invariance

| Check | Status |
|-------|--------|
| Retrieval order unchanged | PASS |
| selected_ids identical | PASS |
| Prompt unchanged | PASS |
| Evidence packet unchanged | PASS |
| Verifier unchanged | PASS |
| Claim gate unchanged | PASS |

---

## Source Smoke

| Source | Status | Shadow Telemetry |
|--------|--------|------------------|
| LocalJsonlLessonStore | COMPLETED | YES |
| FindingsMemoryLessonStore | COMPLETED | YES |
| MemoryRepositoryLessonStore | FAIL_OPEN | YES |

---

## Test Results

| Suite | Result |
|-------|--------|
| BMF10 shadow tests | 11/11 PASS |
| BMF9 shadow tests | 16/16 PASS |
| BMF3 integration | 12/12 PASS |
| H2 anchor | 2/2 PASS |
| Full local_heal | 389/392 (3 pre-existing) |

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |

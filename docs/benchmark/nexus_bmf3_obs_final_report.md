# Nexus BMF3-OBS Replace Global Memory Trace — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BMF3_CTX_SCOPED_MEMORY_TRACE_READY
**Commit**: `348d2581`

---

## Executive Summary

Replaced BMF2 module-level `_last_memory_trace` global with proper ctx-scoped `MemoryTrace` contract. Receipt now reads from adapter class-level trace, no global fallback, no stale leakage.

---

## Problem Solved

BMF2 used `_last_memory_trace` as module-level global:
- Not task-scoped
- Not ctx-scoped
- Not concurrency-safe
- Could leak stale trace across runs
- Receipt imported semantic_anchor_selection global state

---

## Changes

| File | Change |
|------|--------|
| `memory_trace.py` (NEW) | Formal `MemoryTrace` dataclass + `build_memory_trace_from_adapter()` |
| `memory_retrieval_adapter.py` | Added `_last_trace` class variable, stores trace on each retrieval |
| `semantic_anchor_selection.py` | Removed `_last_memory_trace` module global |
| `receipt.py` | Removed `_get_memory_trace_from_scorer()`, added `_extract_memory_trace()` |

---

## Data Flow (After)

```
MemoryRetrievalAdapter.retrieve()
  -> self.last_metadata
  -> MemoryRetrievalAdapter._last_trace (class-level)
  -> receipt._extract_memory_trace(ctx)
  -> receipt.memory_influence (TRACE_AVAILABLE)
```

---

## MemoryTrace Contract

```json
{
  "available": true,
  "trace_status": "TRACE_AVAILABLE",
  "retrieval_source": "LocalJsonlLessonStore",
  "query_text_hash": "a3f2b8c1d4e5...",
  "retrieved_count": 3,
  "selected_ids": ["lh-abc123", "lh-def456"],
  "provenance_count": 2,
  "rerank_mode": true,
  "anchor_symbol": "limit",
  "anchor_file": "sympy/series/limits.py",
  "no_memory_match": false,
  "rejected_without_provenance": 1,
  "influence_status": "NOT_MEASURED",
  "source_contract": "MEMORY_RETRIEVAL_ADAPTER",
  "internal_only": true
}
```

---

## Validation

| Check | Status |
|-------|--------|
| Module global removed | PASS |
| Receipt uses only ctx/adapter trace | PASS |
| selected_ids reconstructible | PASS |
| No stale trace leakage | PASS |
| Prompt unchanged | PASS |
| Ranking unchanged | PASS |
| 19/19 receipt tests | PASS |
| 364/364 full suite | PASS |

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
